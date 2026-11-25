from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from joinproof.contracts import ContractError, load_contract, parse_contract
from joinproof.engine import audit
from joinproof.snapshot import units


class LabCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def model(self, tables, modes=None, scales=None, grains=None):
        relations = []
        for index, rows in enumerate(tables):
            name = f"r{index}"
            with (self.base / f"{name}.csv").open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["key", "value"])
                writer.writerows(rows)
            relations.append(
                {
                    "name": name,
                    "path": f"{name}.csv",
                    "key": ["key"],
                    "grain": (grains or [[]] * len(tables))[index],
                    "measures": [
                        {
                            "name": "amount",
                            "column": "value",
                            "scale": (scales or [0] * len(tables))[index],
                            "conserve": True,
                        }
                    ],
                    "join": "root"
                    if index == 0
                    else (modes or ["left"] * (len(tables) - 1))[index - 1],
                    "key_unique": False,
                }
            )
        raw = {"version": 1, "relations": relations, "preserve_root_rows": True}
        return parse_contract(raw, self.base)

    def test_no_children_conserves(self):
        result = audit(self.model([[("a", "10"), ("b", "-5")]]))
        self.assertTrue(result["passed"])
        self.assertEqual(result["output_rows"], 2)

    def test_many_to_many_exact(self):
        result = audit(self.model([[("a", 10), ("a", 20)], [("a", 2), ("a", 3), ("a", 4)]]))
        self.assertEqual(result["output_rows"], 6)
        self.assertEqual([m["output_units"] for m in result["measures"]], [90, 18])
        self.assertEqual({w["relation"] for w in result["witnesses"]}, {"r0", "r1"})

    def test_left_missing_preserves_root(self):
        result = audit(self.model([[("a", 10)], [("b", 7)]]))
        self.assertEqual(result["output_rows"], 1)
        self.assertEqual(result["measures"][1]["lost_units"], 7)

    def test_inner_missing_loses_root(self):
        result = audit(self.model([[("a", 10)], [("b", 7)]], ["inner"]))
        self.assertEqual(result["output_rows"], 0)
        self.assertEqual(result["measures"][0]["lost_units"], 10)

    def test_null_keys_do_not_match(self):
        result = audit(self.model([[("", 10)], [("", 7), ("", 8)]]))
        self.assertEqual(result["output_rows"], 1)
        self.assertEqual(result["measures"][1]["output_units"], 0)
        self.assertEqual(result["relations"][0]["null_key_rows"], 1)

    def test_whitespace_is_not_trimmed_into_key_match(self):
        result = audit(self.model([[("a ", 10)], [("a", 7)]]))
        self.assertEqual(result["measures"][1]["lost_units"], 7)

    def test_empty_root_loses_all_children(self):
        result = audit(self.model([[], [("a", 7)]]))
        self.assertEqual(result["output_rows"], 0)
        self.assertEqual(result["measures"][1]["lost_units"], 7)

    def test_all_empty(self):
        result = audit(self.model([[], []]))
        self.assertTrue(result["passed"])
        self.assertEqual(result["output_rows"], 0)

    def test_empty_inner_child_blocks_other_children(self):
        result = audit(self.model([[("a", 10)], [], [("a", 7)]], ["inner", "left"]))
        self.assertEqual(result["output_rows"], 0)
        self.assertEqual(result["measures"][2]["lost_units"], 7)

    def test_signed_errors_cancel_but_gate_fails(self):
        result = audit(
            self.model([[("a", 10), ("b", -10)], [("a", 1), ("a", 1), ("b", 1), ("b", 1)]])
        )
        metric = result["measures"][0]
        self.assertEqual(metric["delta_units"], 0)
        self.assertEqual(metric["absolute_exposure_units"], 20)
        self.assertTrue(metric["net_cancellation"])
        self.assertFalse(result["passed"])

    def test_equal_row_counts_can_hide_loss_and_repetition(self):
        result = audit(self.model([[("a", 10), ("b", 10)], [("a", 1), ("a", 1)]], ["inner"]))
        self.assertEqual(result["input_rows"], result["output_rows"])
        self.assertEqual(result["measures"][0]["delta_units"], 0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["relations"][0]["lost_rows"], 1)
        self.assertEqual(result["relations"][0]["repeated_rows"], 1)

    def test_zero_value_duplication_is_structurally_unsafe(self):
        result = audit(self.model([[("a", 0)], [("a", 1), ("a", 2)]]))
        self.assertEqual(result["measures"][0]["absolute_exposure_units"], 0)
        self.assertFalse(result["measures"][0]["safe"])

    def test_null_measure_ignored_in_sum_but_counted_in_source_rows(self):
        result = audit(self.model([[("a", "")], [("a", 1), ("a", 2)]]))
        self.assertEqual(result["measures"][0]["source_nonnull"], 0)
        self.assertEqual(result["measures"][0]["source_units"], 0)
        self.assertFalse(result["passed"])

    def test_grain_duplicate_and_null_are_visible(self):
        contract = self.model([[("a", 1), ("a", 2), ("", 3)]], grains=[["key"]])
        types = {v["type"] for v in audit(contract)["violations"]}
        self.assertEqual(types, {"duplicate_grain", "null_grain"})

    def test_declared_unique_key_checked(self):
        contract = self.model([[("a", 1), ("a", 2), ("", 3)]])
        raw = copy.deepcopy(contract.raw)
        raw["relations"][0]["key_unique"] = True
        types = {v["type"] for v in audit(parse_contract(raw, self.base))["violations"]}
        self.assertEqual(types, {"nonunique_join_key", "null_unique_key"})

    def test_opt_out_measure_and_root_gates_are_explicit(self):
        contract = self.model([[("a", 1)], [("a", 1), ("a", 2)]])
        raw = copy.deepcopy(contract.raw)
        raw["preserve_root_rows"] = False
        raw["relations"][0]["measures"][0]["conserve"] = False
        self.assertTrue(audit(parse_contract(raw, self.base))["passed"])

    def test_minor_units_exact_and_no_rounding(self):
        self.assertEqual(units("123.450", 2), 12345)
        self.assertEqual(units("-0.01", 2), -1)
        self.assertEqual(units("+42", 0), 42)
        self.assertEqual(
            units("99999999999999999999999999999.99", 2), 9999999999999999999999999999999
        )
        for value in ("1.001", "NaN", "inf", "1e2", " 2", "2 ", ".", "１２"):
            with self.subTest(value=value), self.assertRaises(ContractError):
                units(value, 2)

    def test_input_hash_changes_even_for_unused_column(self):
        contract = self.model([[("a", 1)]])
        first = audit(contract)
        p = contract.relations[0].path
        p.write_text("key,value,unused\na,1,extra\n")
        self.assertNotEqual(
            first["relations"][0]["sha256"], audit(contract)["relations"][0]["sha256"]
        )

    def test_deterministic_witness_bound(self):
        contract = self.model([[("a", 10), ("b", 5)], [("a", 1), ("a", 1), ("b", 1), ("b", 1)]])
        first = audit(contract, 1)
        self.assertEqual(first, audit(contract, 1))
        self.assertEqual(len(first["witnesses"]), 1)
        self.assertGreater(first["witness_count"], 1)
        self.assertEqual(audit(contract, 0)["witnesses"], [])
        with self.assertRaises(ValueError):
            audit(contract, -1)

    def test_ragged_or_duplicate_csv_headers_rejected(self):
        contract = self.model([[("a", 1)]])
        for content in ("key,value\na,1,2\n", "key,value\na\n", "key,value,value\na,1,2\n"):
            contract.relations[0].path.write_text(content)
            with self.subTest(content=content), self.assertRaises(ContractError):
                audit(contract)

    def test_strict_contract_rejects_ambiguous_inputs(self):
        contract = self.model([[("a", 1)]])
        modifications = [
            lambda x: x.update(version=2),
            lambda x: x.update(version=True),
            lambda x: x.update(extra=1),
            lambda x: x.update(preserve_root_rows="yes"),
            lambda x: x["relations"][0].update(path="../secret.csv"),
            lambda x: x["relations"][0].update(join="left"),
            lambda x: x["relations"][0].update(key=["key", "key"]),
            lambda x: x["relations"][0].update(key_unique=1),
            lambda x: x["relations"][0]["measures"][0].update(scale=True),
        ]
        for mutate in modifications:
            value = copy.deepcopy(contract.raw)
            mutate(value)
            with self.assertRaises(ContractError):
                parse_contract(value, self.base)

    def test_load_contract_errors_are_clear(self):
        p = self.base / "contract.json"
        with self.assertRaises(ContractError):
            load_contract(p)
        p.write_text("{")
        with self.assertRaises(ContractError):
            load_contract(p)
        contract = self.model([[("a", 1)]])
        p.write_text(json.dumps(contract.raw))
        self.assertEqual(load_contract(p).raw, contract.raw)


if __name__ == "__main__":
    unittest.main()
