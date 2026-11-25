"""CSV snapshots grouped by join key. No raw row text is retained in reports."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import ContractError, Relation

Key = tuple[str | None, ...]


def units(text: str, scale: int) -> int | None:
    """Parse fixed-point values exactly. Blank means SQL NULL, never NaN."""
    if text == "":
        return None
    if len(text) > 64 or not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text, flags=re.ASCII):
        raise ContractError("Measures must be finite fixed-point decimal strings")
    sign = -1 if text.startswith("-") else 1
    whole, _, fraction = text.lstrip("+-").partition(".")
    if any(c != "0" for c in fraction[scale:]):
        raise ContractError("Measure has more precision than the declared scale")
    return sign * (int(whole) * 10**scale + int((fraction[:scale] + "0" * scale)[:scale] or "0"))


@dataclass
class Group:
    rows: int = 0
    sums: dict[str, int] = field(default_factory=dict)
    absolute: dict[str, int] = field(default_factory=dict)
    nonnull: dict[str, int] = field(default_factory=dict)


@dataclass
class Snapshot:
    relation: Relation
    sha256: str
    bytes: int
    rows: int
    groups: dict[Key, Group]
    violations: list[dict]


def read_snapshot(relation: Relation) -> Snapshot:
    try:
        blob = Path(relation.path).read_bytes()
        text = blob.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"Cannot read {relation.name}: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = reader.fieldnames
    required = set(relation.key) | set(relation.grain) | {m.column for m in relation.measures}
    if not fields or len(fields) != len(set(fields)) or not required.issubset(fields):
        raise ContractError(f"{relation.name}: missing or repeated CSV column names")
    groups = {}
    grains = set()
    duplicate_grain_rows = null_grain_rows = row_count = 0
    for row_count, row in enumerate(reader, 1):
        if None in row or any(value is None for value in row.values()):
            raise ContractError(f"{relation.name}: ragged CSV record {row_count}")
        key = tuple(row[k] if row[k] != "" else None for k in relation.key)
        group = groups.setdefault(key, Group())
        group.rows += 1
        if relation.grain:
            grain = tuple(row[k] for k in relation.grain)
            if "" in grain:
                null_grain_rows += 1
            if grain in grains:
                duplicate_grain_rows += 1
            grains.add(grain)
        for measure in relation.measures:
            value = units(row[measure.column], measure.scale)
            name = measure.name
            group.sums[name] = group.sums.get(name, 0) + (value or 0)
            group.absolute[name] = group.absolute.get(name, 0) + abs(value or 0)
            group.nonnull[name] = group.nonnull.get(name, 0) + (value is not None)
    violations = []
    if duplicate_grain_rows:
        violations.append({"type": "duplicate_grain", "rows": duplicate_grain_rows})
    if null_grain_rows:
        violations.append({"type": "null_grain", "rows": null_grain_rows})
    if relation.key_unique:
        duplicate_keys = sum(g.rows > 1 for g in groups.values())
        null_key_rows = sum(g.rows for k, g in groups.items() if None in k)
        if duplicate_keys:
            violations.append({"type": "nonunique_join_key", "keys": duplicate_keys})
        if null_key_rows:
            violations.append({"type": "null_unique_key", "rows": null_key_rows})
    return Snapshot(
        relation, hashlib.sha256(blob).hexdigest(), len(blob), row_count, groups, violations
    )
