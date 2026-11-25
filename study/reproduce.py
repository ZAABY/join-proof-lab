"""Reproduce the pinned Olist study. Raw data and key witnesses stay outside git."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import tempfile
import urllib.request
from pathlib import Path

import duckdb

from joinproof.contracts import parse_contract
from joinproof.engine import audit
from joinproof.evidence import export_atomic, protect_paths

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE / "source-manifest.json").read_text())
SPECS = [
    ("orders", "olist_orders_dataset.csv", ["order_id", "order_purchase_timestamp"], None),
    ("items", "olist_order_items_dataset.csv", ["order_id", "order_item_id", "price"], "price"),
    (
        "payments",
        "olist_order_payments_dataset.csv",
        ["order_id", "payment_sequential", "payment_value"],
        "payment_value",
    ),
    ("reviews", "olist_order_reviews_dataset.csv", ["order_id"], None),
]


def read_inputs(directory, download=False):
    tables = {}
    for spec, record in zip(SPECS, MANIFEST["files"]):
        name, filename, columns, _ = spec
        path = directory / filename
        if not path.exists() and download:
            directory.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(record["url"], timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("Downloaded source hash mismatch")
            path.write_bytes(data)
        data = path.read_bytes()
        if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError(f"Pinned source mismatch: {filename}")
        with io.StringIO(data.decode("utf-8-sig"), newline="") as stream:
            tables[name] = [
                {column: row[column] for column in columns} for row in csv.DictReader(stream)
            ]
    return tables


def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def contract(base, preaggregated=False):
    relations = []
    for index, (name, _, columns, measure) in enumerate(SPECS):
        relations.append(
            {
                "name": name,
                "path": name + ".csv",
                "key": ["order_id"],
                "grain": ["order_id"]
                if preaggregated or index == 0
                else columns[:2]
                if measure
                else [],
                "measures": [
                    {
                        "name": measure,
                        "column": measure,
                        "scale": 0 if preaggregated else 2,
                        "conserve": True,
                    }
                ]
                if measure
                else [],
                "join": "root" if index == 0 else "left",
                "key_unique": preaggregated or index == 0,
            }
        )
    return parse_contract({"version": 1, "relations": relations, "preserve_root_rows": True}, base)


def sql_totals(db, preaggregated=False):
    if preaggregated:
        tables = "orders o LEFT JOIN items_agg i USING(order_id) LEFT JOIN payments_agg p USING(order_id) LEFT JOIN reviews_agg r USING(order_id)"
        item, payment = "i.price", "p.payment_value"
    else:
        tables = "orders o LEFT JOIN items i USING(order_id) LEFT JOIN payments p USING(order_id) LEFT JOIN reviews r USING(order_id)"
        item = "CAST(i.price AS DECIMAL(18,2))*100"
        payment = "CAST(p.payment_value AS DECIMAL(18,2))*100"
    rows, items, payments, distinct_payments = db.execute(
        f"SELECT count(*), coalesce(sum({item}),0), coalesce(sum({payment}),0), coalesce(sum(DISTINCT {payment}),0) FROM {tables}"
    ).fetchone()
    return {
        "output_rows": rows,
        "items_units": int(items),
        "payments_units": int(payments),
        "distinct_payments_units": int(distinct_payments),
    }


def one_cohort(tables, month):
    orders = (
        tables["orders"]
        if month == "all"
        else [r for r in tables["orders"] if r["order_purchase_timestamp"][:7] == month]
    )
    keys = {row["order_id"] for row in orders}
    selected = {"orders": orders}
    selected.update(
        {
            name: [r for r in tables[name] if r["order_id"] in keys]
            for name in ("items", "payments", "reviews")
        }
    )
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        db = duckdb.connect()
        try:
            for name, _, columns, _ in SPECS:
                path = base / (name + ".csv")
                write_csv(path, selected[name], columns)
                db.execute(
                    f"CREATE TABLE {name} AS SELECT * FROM read_csv(?, all_varchar=true)",
                    [str(path)],
                )
            naive = audit(contract(base), witness_limit=0)
            naive_sql = sql_totals(db)
            for metric, result in zip(("items_units", "payments_units"), naive["measures"]):
                if result["output_units"] != naive_sql[metric]:
                    raise AssertionError("Naive factorization does not match SQL")
            if naive["output_rows"] != naive_sql["output_rows"]:
                raise AssertionError("Naive row prediction does not match SQL")
            for name, _, _, measure in SPECS[1:]:
                projection = (
                    f", CAST(sum(CAST({measure} AS DECIMAL(18,2))*100) AS BIGINT) AS {measure}"
                    if measure
                    else ""
                )
                db.execute(
                    f"CREATE TABLE {name}_agg AS SELECT order_id{projection} FROM {name} GROUP BY order_id"
                )
            fixed_sql = sql_totals(db, preaggregated=True)
            for name, _, _, measure in SPECS[1:]:
                cursor = db.execute(f"SELECT * FROM {name}_agg ORDER BY order_id")
                columns = [d[0] for d in cursor.description]
                write_csv(
                    base / (name + ".csv"),
                    [dict(zip(columns, r)) for r in cursor.fetchall()],
                    columns,
                )
            fixed = audit(contract(base, preaggregated=True), witness_limit=0)
            if (
                not fixed["passed"]
                or fixed["output_rows"] != len(orders)
                or fixed_sql["output_rows"] != len(orders)
            ):
                raise AssertionError("Explicit preaggregation failed its configured gate")
            for metric, original, aggregated in zip(
                ("items_units", "payments_units"), naive["measures"], fixed["measures"]
            ):
                if (
                    original["source_units"] != aggregated["output_units"]
                    or aggregated["output_units"] != fixed_sql[metric]
                ):
                    raise AssertionError("Preaggregation does not conserve selected source totals")
            return {
                "cohort": month,
                "source_rows": {name: len(rows) for name, rows in selected.items()},
                "naive_gate_passed": naive["passed"],
                "preaggregated_gate_passed": fixed["passed"],
                "naive_sql": naive_sql,
                "preaggregated_sql": fixed_sql,
                "measures": [
                    {
                        k: row[k]
                        for k in (
                            "relation",
                            "measure",
                            "source_units",
                            "output_units",
                            "delta_units",
                            "absolute_exposure_units",
                            "affected_nonnull_rows",
                        )
                    }
                    for row in naive["measures"]
                ],
                "naive_row_count_check_passed": naive["input_rows"] == naive["output_rows"],
                "naive_payment_total_check_passed": naive["measures"][1]["delta_units"] == 0,
                "sum_distinct_payment_correct": naive_sql["distinct_payments_units"]
                == naive["measures"][1]["source_units"],
                "sql_factorization_equal": True,
            }
        finally:
            db.close()


def run(directory, download=False):
    tables = read_inputs(directory, download)
    root_keys = {row["order_id"] for row in tables["orders"]}
    orphans = {
        name: sum(row["order_id"] not in root_keys for row in rows)
        for name, rows in tables.items()
        if name != "orders"
    }
    months = sorted({row["order_purchase_timestamp"][:7] for row in tables["orders"]})
    cohorts = [one_cohort(tables, month) for month in ["all", *months]]
    if any(
        sum(c["source_rows"][name] for c in cohorts[1:]) != cohorts[0]["source_rows"][name]
        for name in tables
    ):
        raise AssertionError("Month partitions do not reconstruct the full selected population")
    return {
        "schema_version": 1,
        "license": "CC-BY-NC-SA-4.0",
        "dataset_commit": MANIFEST["commit"],
        "duckdb_version": duckdb.__version__,
        "cohort_definition": "Order purchase month; child rows restricted to that order population, never child event month",
        "orphan_rows_excluded_from_cohorts": orphans,
        "cohorts": cohorts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download only missing pinned inputs; no network without this flag",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protect_paths(
        [args.data_directory / record["name"] for record in MANIFEST["files"]], None, args.output
    )
    if args.output.exists():
        raise ValueError("Output already exists; choose a new path")
    result = run(args.data_directory, args.download)
    export_atomic(args.output, result)
    print(
        f"Verified {len(result['cohorts'])} cohorts; {len(result['cohorts']) * 2} SQL/audit plan comparisons"
    )
