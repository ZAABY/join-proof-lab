from __future__ import annotations

import contextlib
import copy
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_core

from joinproof.cli import main
from joinproof.engine import audit, canonical
from joinproof.evidence import EvidenceError, Ledger, digest, export_atomic, identity, protect_paths
from joinproof.recover import main as recover


class EvidenceCases(unittest.TestCase):
    def setUp(self):
        fixture = test_core.LabCase()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.base = fixture.base
        self.contract = fixture.model([[("a", 10)], [("a", 2), ("a", 3)]])
        self.result = audit(self.contract)
        self.path = self.base / "evidence.sqlite"
        self.ledger = Ledger(self.path)
        self.addCleanup(self.ledger.close)

    def invoke(self, *options):
        path = self.base / "contract.json"
        path.write_text(json.dumps(self.contract.raw))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(path), *map(str, options)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_foreign_database_refused_without_new_tables(self):
        path = self.base / "foreign.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE unrelated (value TEXT)")
        with self.assertRaises(EvidenceError):
            Ledger(path)
        with sqlite3.connect(path) as db:
            self.assertEqual(
                db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                [("unrelated",)],
            )

    def test_readonly_recovery_and_missing_database(self):
        run = self.ledger.complete(self.ledger.start(), self.result)
        output = self.base / "recovered.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(recover([str(self.path), run, "--output", str(output)]), 0)
        self.assertEqual(json.loads(output.read_text()), self.result)
        missing = self.base / "missing.sqlite"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(recover([str(missing), run]), 3)
        self.assertFalse(missing.exists())

    def test_recovery_rejects_ledger_and_sidecar_aliases(self):
        run = self.ledger.complete(self.ledger.start(), self.result)
        for suffix in ("", "-wal", "-shm", "-journal"):
            path = str(self.path) + suffix
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(recover([str(self.path), run, "--output", path]), 3)
        self.assertEqual(self.ledger.verify(run), self.result)

    def test_symlink_ledger_protects_actual_sidecars(self):
        alias = self.base / "alias.sqlite"
        alias.symlink_to(self.path)
        target_sidecar = self.base / "evidence.sqlite-wal"
        with self.assertRaises(EvidenceError):
            protect_paths([target_sidecar], alias, None)
        with self.assertRaises(EvidenceError):
            protect_paths([], alias, target_sidecar)
        protect_paths([], alias, self.base / "safe.json")

    def test_incompatible_layout_rejected_before_attempt(self):
        self.ledger.db.execute("ALTER TABLE runs ADD COLUMN unexpected TEXT")
        self.ledger.db.commit()
        with self.assertRaises(EvidenceError):
            Ledger(self.path)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)

    def test_repeatable_run_distinct_attempts(self):
        first, second = self.ledger.start(), self.ledger.start()
        self.assertNotEqual(first, second)
        run = self.ledger.complete(first, self.result)
        self.assertEqual(run, self.ledger.complete(second, self.result))
        self.assertEqual(self.ledger.verify(run), self.result)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM runs").fetchone()[0], 1)
        self.assertEqual(
            self.ledger.db.execute(
                "SELECT count(*) FROM attempts WHERE state='completed'"
            ).fetchone()[0],
            2,
        )

    def test_changed_bytes_and_witness_policy_change_identity(self):
        for change in ("bytes", "witness_limit", "contract_sha256", "engine_version"):
            changed = copy.deepcopy(self.result)
            if change == "bytes":
                changed["relations"][0]["sha256"] = "0" * 64
            elif change == "witness_limit":
                changed[change] += 1
            else:
                changed[change] += "different"
            self.assertNotEqual(digest(identity(changed)), digest(identity(self.result)))

    def test_conflicting_result_rolls_back_but_retains_running_attempt(self):
        first = self.ledger.start()
        self.ledger.complete(first, self.result)
        second = self.ledger.start()
        changed = copy.deepcopy(self.result)
        changed["output_rows"] += 1
        with self.assertRaises(EvidenceError):
            self.ledger.complete(second, changed)
        self.assertEqual(
            self.ledger.db.execute(
                "SELECT state FROM attempts WHERE attempt_id=?", (second,)
            ).fetchone()[0],
            "running",
        )
        self.ledger.fail(second, "EvidenceError")
        self.assertEqual(
            self.ledger.db.execute(
                "SELECT state FROM attempts WHERE attempt_id=?", (second,)
            ).fetchone()[0],
            "failed",
        )

    def test_invalid_attempt_rolls_back_result_insert(self):
        with self.assertRaises(EvidenceError):
            self.ledger.complete("absent", self.result)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)

    def test_double_completion_and_fail_rejected(self):
        attempt = self.ledger.start()
        self.ledger.complete(attempt, self.result)
        with self.assertRaises(EvidenceError):
            self.ledger.complete(attempt, self.result)
        with self.assertRaises(EvidenceError):
            self.ledger.fail(attempt, "error")

    def test_interrupted_attempt_survives_reopen_and_new_attempt_completes(self):
        attempt = self.ledger.start()
        other = Ledger(self.path)
        try:
            self.assertEqual(
                other.db.execute(
                    "SELECT state FROM attempts WHERE attempt_id=?", (attempt,)
                ).fetchone()[0],
                "running",
            )
            run = other.complete(other.start(), self.result)
            self.assertEqual(other.verify(run), self.result)
        finally:
            other.close()

    def test_payload_corruption_detected(self):
        run = self.ledger.complete(self.ledger.start(), self.result)
        self.ledger.db.execute("UPDATE runs SET result_json='{}'")
        self.ledger.db.commit()
        with self.assertRaises(EvidenceError):
            self.ledger.verify(run)

    def test_changed_result_with_recomputed_hash_conflicts_with_identity(self):
        run = self.ledger.complete(self.ledger.start(), self.result)
        changed = copy.deepcopy(self.result)
        changed["contract_sha256"] = "0" * 64
        self.ledger.db.execute(
            "UPDATE runs SET result_json=?, result_sha256=?", (canonical(changed), digest(changed))
        )
        self.ledger.db.commit()
        with self.assertRaises(EvidenceError):
            self.ledger.verify(run)

    def test_bad_version_and_missing_run(self):
        with self.assertRaises(EvidenceError):
            self.ledger.verify("missing")
        self.ledger.db.execute("UPDATE metadata SET version=99")
        self.ledger.db.commit()
        with self.assertRaises(EvidenceError):
            Ledger(self.path)

    def test_atomic_export_and_no_clobber(self):
        target = self.base / "report.json"
        export_atomic(target, self.result)
        self.assertEqual(json.loads(target.read_text()), self.result)
        with self.assertRaises(FileExistsError):
            export_atomic(target, {})
        self.assertEqual(json.loads(target.read_text()), self.result)
        self.assertFalse(list(self.base.glob(".joinproof-*")))

    def test_export_link_failure_cleans_temporary_and_keeps_target_absent(self):
        target = self.base / "report.json"
        with (
            patch("joinproof.evidence.os.link", side_effect=OSError("injected link failure")),
            self.assertRaises(OSError),
        ):
            export_atomic(target, self.result)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.base.glob(".joinproof-*")))

    def test_export_serialization_failure_cleans_temporary(self):
        with self.assertRaises(TypeError):
            export_atomic(self.base / "bad.json", {"bad": object()})
        self.assertFalse(list(self.base.glob(".joinproof-*")))

    def test_path_aliases_and_sidecars_rejected(self):
        source = self.contract.relations[0].path
        alias = self.base / "alias"
        alias.symlink_to(source)
        hardlink = self.base / "hardlink"
        hardlink.hardlink_to(source)
        for path in (source, alias, hardlink):
            with self.assertRaises(EvidenceError):
                protect_paths([source], path, None)
            with self.assertRaises(EvidenceError):
                protect_paths([source], None, path)
        with self.assertRaises(EvidenceError):
            protect_paths([self.base / "x-wal"], self.base / "x", None)
        with self.assertRaises(EvidenceError):
            protect_paths([], self.path, self.path)

    def test_cli_persists_failed_gate_and_exports_same_result(self):
        output = self.base / "output.json"
        code, stdout, stderr = self.invoke("--ledger", self.path, "--output", output)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout), json.loads(output.read_text()))
        self.assertIn("Evidence run", stderr)
        run = self.ledger.db.execute("SELECT run_id FROM runs").fetchone()[0]
        self.assertEqual(self.ledger.verify(run), json.loads(stdout))

    def test_cli_export_failure_leaves_recoverable_completed_ledger(self):
        with patch("joinproof.cli.export_atomic", side_effect=OSError("injected")):
            code, stdout, stderr = self.invoke(
                "--ledger", self.path, "--output", self.base / "out.json"
            )
        self.assertEqual(code, 3)
        self.assertEqual(stdout, "")
        self.assertIn("ledger evidence retained", stderr)
        run = self.ledger.db.execute("SELECT run_id FROM runs").fetchone()[0]
        self.assertEqual(self.ledger.verify(run), self.result)

    def test_cli_audit_failure_marks_attempt_failed(self):
        with patch("joinproof.cli.audit", side_effect=ValueError("injected")):
            code, stdout, stderr = self.invoke("--ledger", self.path)
        self.assertEqual(code, 3)
        self.assertEqual(stdout, "")
        self.assertIn("injected", stderr)
        self.assertEqual(
            self.ledger.db.execute("SELECT state FROM attempts").fetchone()[0], "failed"
        )
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)

    def test_cli_rejects_input_alias_before_sqlite_open(self):
        source = self.contract.relations[0].path
        before = source.read_bytes()
        code, _, _ = self.invoke("--ledger", source)
        self.assertEqual(code, 3)
        self.assertEqual(source.read_bytes(), before)

    def test_cli_existing_output_not_overwritten(self):
        output = self.base / "exists.json"
        output.write_text("existing")
        code, _, _ = self.invoke("--output", output)
        self.assertEqual(code, 3)
        self.assertEqual(output.read_text(), "existing")


if __name__ == "__main__":
    unittest.main()
