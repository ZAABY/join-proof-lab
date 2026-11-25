from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "olist_study", Path(__file__).resolve().parents[1] / "study" / "reproduce.py"
)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class StudyCases(unittest.TestCase):
    def test_distinct_removes_legitimate_equal_payments(self):
        tables = {
            "orders": [
                {"order_id": k, "order_purchase_timestamp": "2020-01-01"} for k in ("a", "b")
            ],
            "items": [{"order_id": "a", "order_item_id": str(i), "price": "10.00"} for i in (1, 2)],
            "payments": [
                {"order_id": k, "payment_sequential": "1", "payment_value": "50.00"}
                for k in ("a", "b")
            ],
            "reviews": [{"order_id": "a"}, {"order_id": "a"}],
        }
        result = study.one_cohort(tables, "2020-01")
        self.assertFalse(result["naive_gate_passed"])
        self.assertTrue(result["preaggregated_gate_passed"])
        self.assertEqual(result["naive_sql"]["payments_units"], 25000)
        self.assertEqual(result["naive_sql"]["distinct_payments_units"], 5000)
        self.assertEqual(result["preaggregated_sql"]["payments_units"], 10000)

    def test_empty_child_tables_and_empty_month(self):
        tables = {
            "orders": [{"order_id": "a", "order_purchase_timestamp": "2020-01-01"}],
            "items": [],
            "payments": [],
            "reviews": [],
        }
        self.assertTrue(study.one_cohort(tables, "all")["preaggregated_gate_passed"])
        result = study.one_cohort(tables, "1999-01")
        self.assertEqual(result["naive_sql"]["output_rows"], 0)
        self.assertTrue(result["naive_gate_passed"])


if __name__ == "__main__":
    unittest.main()
