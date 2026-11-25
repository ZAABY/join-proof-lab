"""Exact star-join row/measure diagnostics through per-key factorization.

Each child joins directly to the root key with ordinary SQL equality.
These equations are not a new algorithm; see docs/prior-art.md.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from math import prod

from .contracts import Contract
from .snapshot import Snapshot, read_snapshot


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def audit(contract: Contract, witness_limit: int = 12) -> dict:
    return audit_snapshots(contract, [read_snapshot(r) for r in contract.relations], witness_limit)


def audit_snapshots(contract: Contract, snapshots: list[Snapshot], witness_limit: int = 12) -> dict:
    if type(witness_limit) is not int or not 0 <= witness_limit <= 1000:
        raise ValueError("witness_limit must be from 0 to 1000")
    if len(snapshots) != len(contract.relations) or any(
        s.relation != r for s, r in zip(snapshots, contract.relations)
    ):
        raise ValueError("Snapshots must match the declared relations in order")
    copies = [{} for _ in snapshots]
    root = snapshots[0]
    output_rows = 0
    for key, group in root.groups.items():
        counts = [
            s.groups[key].rows if None not in key and key in s.groups else 0 for s in snapshots[1:]
        ]
        factors = [
            max(n, 1) if s.relation.join == "left" else n for n, s in zip(counts, snapshots[1:])
        ]
        root_copies = prod(factors)
        copies[0][key] = root_copies
        output_rows += group.rows * root_copies
        for index, count in enumerate(counts):
            if count:
                copies[index + 1][key] = group.rows * prod(
                    factor for j, factor in enumerate(factors) if j != index
                )
    results = []
    measures = []
    violations = []
    heap = []
    witness_count = 0
    for snapshot, multipliers in zip(snapshots, copies):
        name = snapshot.relation.name
        lost_rows = repeated_rows = null_key_rows = 0
        metric_rows = {
            m.name: {
                "source_units": 0,
                "output_units": 0,
                "lost_units": 0,
                "repeated_units": 0,
                "absolute_exposure_units": 0,
                "source_nonnull": 0,
                "output_nonnull": 0,
                "affected_nonnull_rows": 0,
            }
            for m in snapshot.relation.measures
        }
        for key, group in snapshot.groups.items():
            multiplier = multipliers.get(key, 0)
            lost_rows += group.rows if multiplier == 0 else 0
            repeated_rows += group.rows * max(multiplier - 1, 0)
            null_key_rows += group.rows if None in key else 0
            key_exposure = 0
            for m in snapshot.relation.measures:
                row = metric_rows[m.name]
                value = group.sums[m.name]
                absolute_exposure = group.absolute[m.name] * abs(multiplier - 1)
                row["source_units"] += value
                row["output_units"] += value * multiplier
                row["lost_units"] += value if multiplier == 0 else 0
                row["repeated_units"] += value * max(multiplier - 1, 0)
                row["absolute_exposure_units"] += absolute_exposure
                row["source_nonnull"] += group.nonnull[m.name]
                row["output_nonnull"] += group.nonnull[m.name] * multiplier
                row["affected_nonnull_rows"] += group.nonnull[m.name] if multiplier != 1 else 0
                key_exposure += absolute_exposure
            if multiplier != 1:
                witness_count += 1
                witness = {
                    "relation": name,
                    "key": list(key),
                    "source_rows": group.rows,
                    "copies_per_source_row": multiplier,
                    "output_contributions": group.rows * multiplier,
                    "source_measure_units": group.sums,
                    "reason": "dropped" if multiplier == 0 else "repeated",
                }
                # Stable tie-breaker; keys are data, never SQL expressions.
                entry = (key_exposure, group.rows * abs(multiplier - 1), canonical(witness))
                if witness_limit:
                    if len(heap) < witness_limit:
                        heapq.heappush(heap, entry)
                    elif entry > heap[0]:
                        heapq.heapreplace(heap, entry)
        for m in snapshot.relation.measures:
            row = metric_rows[m.name]
            delta = row["output_units"] - row["source_units"]
            if delta != row["repeated_units"] - row["lost_units"]:
                raise AssertionError("Internal source/loss/repetition identity failed")
            safe = row["affected_nonnull_rows"] == 0
            measures.append(
                {
                    "relation": name,
                    "measure": m.name,
                    "scale": m.scale,
                    "require_conservation": m.conserve,
                    **row,
                    "delta_units": delta,
                    "net_cancellation": delta == 0 and row["absolute_exposure_units"] > 0,
                    "safe": safe,
                }
            )
            if m.conserve and not safe:
                violations.append(
                    {
                        "type": "measure_multiplicity",
                        "relation": name,
                        "measure": m.name,
                        "affected_rows": row["affected_nonnull_rows"],
                    }
                )
        violations.extend({"relation": name, **v} for v in snapshot.violations)
        results.append(
            {
                "name": name,
                "rows": snapshot.rows,
                "key_groups": len(snapshot.groups),
                "null_key_rows": null_key_rows,
                "lost_rows": lost_rows,
                "repeated_rows": repeated_rows,
                "sha256": snapshot.sha256,
                "bytes": snapshot.bytes,
            }
        )
    root_lost = results[0]["lost_rows"]
    root_repeated = results[0]["repeated_rows"]
    if contract.preserve_root_rows and (root_lost or root_repeated):
        violations.append(
            {
                "type": "root_row_multiplicity",
                "lost_rows": root_lost,
                "repeated_rows": root_repeated,
            }
        )
    contract_hash = hashlib.sha256(canonical(contract.raw).encode()).hexdigest()
    return {
        "schema_version": 1,
        "engine_version": "0.1.0",
        "contract_sha256": contract_hash,
        "input_rows": root.rows,
        "output_rows": output_rows,
        "relations": results,
        "measures": measures,
        "violations": violations,
        "passed": not violations,
        "witness_count": witness_count,
        "witness_limit": witness_limit,
        "witnesses": [json.loads(item[2]) for item in sorted(heap, reverse=True)],
        "semantics": {
            "shape": "root-key star equijoin",
            "keys": "text, blank is NULL",
            "null_equality": "SQL =, NULL never matches",
            "sum": "exact integer minor units, SQL NULL ignored, empty sum normalized to 0",
            "safe": "each non-null source measure row contributes exactly once",
            "limits": "no predicates, key coercion, cyclic/range joins or inferred repairs",
        },
    }
