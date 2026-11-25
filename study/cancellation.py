"""Explicit signed cancellation fixture, independently checked with executed SQL."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from joinproof.contracts import load_contract
from joinproof.engine import audit

ROOT = Path(__file__).resolve().parents[1]


def evaluate():
    cases = []
    for folder in ("cancellation", "signed-cancellation"):
        directory = ROOT / "examples" / folder
        result = audit(load_contract(directory / "contract.json"))
        with duckdb.connect() as db:
            source = db.execute(
                "SELECT count(*), sum(CAST(amount AS DECIMAL(18,2))*100) FROM read_csv(?, all_varchar=true)",
                [str(directory / "orders.csv")],
            ).fetchone()
            joined = db.execute(
                "SELECT count(*), sum(CAST(o.amount AS DECIMAL(18,2))*100) FROM read_csv(?, all_varchar=true) o INNER JOIN read_csv(?, all_varchar=true) e USING(order_id)",
                [str(directory / "orders.csv"), str(directory / "events.csv")],
            ).fetchone()
            contribution_rows = db.execute(
                "SELECT o.order_id, count(e.event_id) AS copies FROM read_csv(?, all_varchar=true) o LEFT JOIN read_csv(?, all_varchar=true) e USING(order_id) GROUP BY o.order_id ORDER BY o.order_id",
                [str(directory / "orders.csv"), str(directory / "events.csv")],
            ).fetchall()
        assert result["output_rows"] == joined[0]
        assert result["measures"][0]["source_units"] == int(source[1])
        assert result["measures"][0]["output_units"] == int(joined[1])
        assert source == joined and not result["passed"]
        assert result["measures"][0]["absolute_exposure_units"] > 0
        assert any(copies != 1 for _, copies in contribution_rows)
        cases.append(
            {
                "fixture": folder,
                "synthetic": True,
                "source_rows": source[0],
                "output_rows": joined[0],
                "source_units": int(source[1]),
                "output_units": int(joined[1]),
                "exposure_units": result["measures"][0]["absolute_exposure_units"],
                "gate_passed": result["passed"],
                "sql_copies": [{"order_id": k, "copies": n} for k, n in contribution_rows],
            }
        )
    return {"schema_version": 1, "license": "MIT", "cases": cases}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
