from __future__ import annotations

import importlib.util
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "study" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href")


class ReportCases(unittest.TestCase):
    def test_controlled_cancellation_matches_saved_evidence_and_sql(self):
        result = load("cancellation").evaluate()
        self.assertEqual(result, json.loads((ROOT / "study/results/cancellation.json").read_text()))
        self.assertEqual(result["cases"][1]["exposure_units"], 30000)

    def test_report_matches_evidence_and_links_resolve_locally(self):
        source = (ROOT / "report/index.html").read_text()
        self.assertEqual(source, load("report").render())
        for expected in (
            "20,579,664.01",
            "16,008,872.12",
            "7,773,585.14",
            "300.00",
            "CC BY-NC-SA 4.0",
            "no extra real-data detection claim",
        ):
            self.assertIn(expected, source)
        self.assertNotIn("@CARDS@", source)
        parser = LinkParser()
        parser.feed(source)
        for link in parser.links:
            if not link.startswith("https:"):
                self.assertTrue((ROOT / "report" / link).exists(), link)


if __name__ == "__main__":
    unittest.main()
