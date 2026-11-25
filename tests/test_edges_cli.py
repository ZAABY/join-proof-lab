from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path

import test_core

from joinproof.cli import main
from joinproof.contracts import ContractError, load_contract, parse_contract
from joinproof.engine import audit


class ExtraCases(unittest.TestCase):
    def setUp(self):
        self.fixture = test_core.LabCase()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_contract_identity_cannot_be_mutated_after_parsing(self):
        contract = self.fixture.model([[("a", 1)]])
        value = contract.raw
        again = parse_contract(value, self.fixture.base)
        before = audit(again)
        value["preserve_root_rows"] = False
        again.raw["version"] = 99
        self.assertEqual(audit(again), before)

    def test_repeated_json_field_rejected(self):
        p = self.fixture.base / "bad.json"
        p.write_text('{"version":1,"version":1}')
        with self.assertRaises(ContractError):
            load_contract(p)

    def test_composite_keys_do_not_collide_by_concatenation(self):
        c = self.fixture.model([[("a", 1)], [("a", 1)]])
        for filename, content in [
            ("r0.csv", "a,b,value\nx|y,z,10\nx,y|z,20\n"),
            ("r1.csv", "a,b,value\nx|y,z,7\nx|y,z,8\n"),
        ]:
            (self.fixture.base / filename).write_text(content)
        raw = c.raw
        for r in raw["relations"]:
            r["key"] = ["a", "b"]
        result = audit(parse_contract(raw, self.fixture.base))
        self.assertEqual(result["output_rows"], 3)
        self.assertEqual(result["measures"][0]["output_units"], 40)

    def test_snapshot_identity_with_bom_and_leading_zero_key(self):
        c = self.fixture.model([[("01", 1)], [("1", 2)]])
        p = c.relations[0].path
        p.write_bytes(b"\xef\xbb\xbfkey,value\n01,1\n")
        result = audit(c)
        self.assertEqual(result["measures"][1]["lost_units"], 2)
        self.assertEqual(
            result["relations"][0]["sha256"], hashlib.sha256(p.read_bytes()).hexdigest()
        )

    def test_cli_good_bad_and_invalid_inputs(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        for folder, expected in [("cancellation", 2), ("preaggregated", 0)]:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main([str(examples / folder / "contract.json")])
            self.assertEqual(code, expected)
            self.assertEqual(json.loads(stdout.getvalue())["passed"], expected == 0)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(self.fixture.base / "missing.json")])
        self.assertEqual(code, 3)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Invalid audit input", stderr.getvalue())

    def test_cli_does_not_change_source_files(self):
        c = self.fixture.model([[("a", 1)]])
        p = self.fixture.base / "contract.json"
        p.write_text(json.dumps(c.raw))
        before = {file.name: file.read_bytes() for file in self.fixture.base.iterdir()}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(p)]), 0)
        self.assertEqual(
            before, {file.name: file.read_bytes() for file in self.fixture.base.iterdir()}
        )


if __name__ == "__main__":
    unittest.main()
