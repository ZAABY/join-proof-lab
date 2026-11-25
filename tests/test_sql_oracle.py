"""Seeded differential checks: factorized arithmetic vs executed DuckDB SQL.

This is a bounded randomized test, not a mathematical proof for all inputs.
"""

from __future__ import annotations

import csv
import importlib.util
import random
import tempfile
import unittest
from pathlib import Path

from joinproof.contracts import parse_contract
from joinproof.engine import audit


@unittest.skipUnless(
    importlib.util.find_spec("duckdb"), "Install the dev extra for SQL oracle tests"
)
class SQLOracle(unittest.TestCase):
    def test_seeded_star_queries(self):
        import duckdb

        rng = random.Random(20261122)
        with tempfile.TemporaryDirectory() as folder, duckdb.connect() as c:
            base = Path(folder)
            for trial in range(600):
                with self.subTest(trial=trial):
                    arity = 1 + trial % 2
                    count = rng.randrange(1, 5)
                    relations = []
                    for i in range(count):
                        c.execute(f"DROP TABLE IF EXISTS r{i}")
                        c.execute(f"CREATE TABLE r{i}(k0 VARCHAR, k1 VARCHAR, value BIGINT)")
                        records = []
                        for _ in range(rng.randrange(9)):
                            keys = [rng.choice([None, "0", "1", "2"]) for _ in range(arity)]
                            if arity == 1:
                                keys.append("unused")
                            records.append((*keys, rng.choice([None, -200, -100, 0, 100, 200])))
                        if records:
                            c.executemany(f"INSERT INTO r{i} VALUES (?,?,?)", records)
                        with (base / f"r{i}.csv").open("w", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow(["k0", "k1", "value"])
                            writer.writerows(records)
                        relations.append(
                            {
                                "name": f"r{i}",
                                "path": f"r{i}.csv",
                                "key": ["k0", "k1"][:arity],
                                "grain": [],
                                "join": "root" if i == 0 else rng.choice(["left", "inner"]),
                                "key_unique": False,
                                "measures": [
                                    {
                                        "name": "value",
                                        "column": "value",
                                        "scale": 0,
                                        "conserve": True,
                                    }
                                ],
                            }
                        )
                    result = audit(
                        parse_contract(
                            {"version": 1, "relations": relations, "preserve_root_rows": True}, base
                        )
                    )
                    # Query structure is generated from fixed internal identifiers, never user SQL.
                    query = (
                        "SELECT COUNT(*)"
                        + "".join(f",COALESCE(SUM(r{i}.value),0)" for i in range(count))
                        + " FROM r0"
                    )
                    for i, r in enumerate(relations[1:], 1):
                        query += f" {r['join'].upper()} JOIN r{i} ON r0.k0=r{i}.k0"
                        if arity == 2:
                            query += f" AND r0.k1=r{i}.k1"
                    actual = c.execute(query).fetchone()
                    self.assertEqual(result["output_rows"], actual[0])
                    self.assertEqual(
                        [m["output_units"] for m in result["measures"]], list(actual[1:])
                    )
                    for measure in result["measures"]:
                        self.assertEqual(
                            measure["delta_units"],
                            measure["repeated_units"] - measure["lost_units"],
                        )


if __name__ == "__main__":
    unittest.main()
