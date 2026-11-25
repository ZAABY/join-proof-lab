"""Local evidence ledger. Hashes detect accidents, not a malicious database editor."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .engine import canonical


class EvidenceError(ValueError):
    """Stored evidence is incompatible, incomplete or inconsistent."""


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def identity(result: dict) -> dict:
    return {
        "schema_version": result["schema_version"],
        "engine_version": result["engine_version"],
        "contract_sha256": result["contract_sha256"],
        "inputs": [
            {k: relation[k] for k in ("name", "sha256", "bytes")}
            for relation in result["relations"]
        ],
        "witness_limit": result["witness_limit"],
    }


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    """One SQLite transaction commits a result and its completed attempt together.

    Starting an attempt commits separately, so interrupted attempts remain visible.
    No claim is made of a transaction spanning SQLite and exported files.
    """

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, timeout=5)
        try:
            self.db.execute("PRAGMA foreign_keys=ON")
            tables = {
                row[0]
                for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if tables and tables != {"metadata", "runs", "attempts"}:
                raise EvidenceError("Not a Join Proof Lab ledger")
            if tables:
                expected_columns = {
                    "metadata": ["version"],
                    "runs": ["run_id", "identity_json", "result_json", "result_sha256"],
                    "attempts": [
                        "attempt_id",
                        "started_at",
                        "finished_at",
                        "state",
                        "run_id",
                        "error",
                    ],
                }
                for table, expected in expected_columns.items():
                    actual = [row[1] for row in self.db.execute(f"PRAGMA table_info({table})")]
                    if actual != expected:
                        raise EvidenceError("Incompatible ledger table layout")
            with self.db:
                self.db.execute("CREATE TABLE IF NOT EXISTS metadata (version INTEGER NOT NULL)")
                versions = self.db.execute("SELECT version FROM metadata").fetchall()
                if not versions:
                    self.db.execute("INSERT INTO metadata VALUES (1)")
                elif versions != [(1,)]:
                    raise EvidenceError("Unsupported ledger version")
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, "
                    "identity_json TEXT NOT NULL, result_json TEXT NOT NULL, "
                    "result_sha256 TEXT NOT NULL)"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS attempts (attempt_id TEXT PRIMARY KEY, "
                    "started_at TEXT NOT NULL, finished_at TEXT, state TEXT NOT NULL "
                    "CHECK(state IN ('running','completed','failed')), "
                    "run_id TEXT REFERENCES runs(run_id), error TEXT)"
                )
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def start(self) -> str:
        attempt = str(uuid.uuid4())
        with self.db:
            self.db.execute(
                "INSERT INTO attempts VALUES (?, ?, NULL, 'running', NULL, NULL)", (attempt, now())
            )
        return attempt

    def fail(self, attempt: str, error: str):
        with self.db:
            changed = self.db.execute(
                "UPDATE attempts SET state='failed', finished_at=?, error=? "
                "WHERE attempt_id=? AND state='running'",
                (now(), error, attempt),
            ).rowcount
            if changed != 1:
                raise EvidenceError("Attempt is absent or no longer running")

    def complete(self, attempt: str, result: dict) -> str:
        run_identity = identity(result)
        run_id = digest(run_identity)
        payload, checksum = canonical(result), digest(result)
        with self.db:
            existing = self.db.execute(
                "SELECT identity_json, result_json, result_sha256 FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            expected = (canonical(run_identity), payload, checksum)
            if existing is not None and existing != expected:
                raise EvidenceError("Existing run conflicts with deterministic result")
            self.db.execute("INSERT OR IGNORE INTO runs VALUES (?, ?, ?, ?)", (run_id, *expected))
            changed = self.db.execute(
                "UPDATE attempts SET state='completed', finished_at=?, run_id=? "
                "WHERE attempt_id=? AND state='running'",
                (now(), run_id, attempt),
            ).rowcount
            if changed != 1:
                raise EvidenceError("Attempt is absent or no longer running")
        return run_id

    def verify(self, run_id: str) -> dict:
        row = self.db.execute(
            "SELECT identity_json, result_json, result_sha256 FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise EvidenceError("Run not found")
        try:
            stored_identity, result = json.loads(row[0]), json.loads(row[1])
            valid = (
                digest(result) == row[2]
                and identity(result) == stored_identity
                and digest(stored_identity) == run_id
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceError("Malformed stored evidence") from exc
        if not valid:
            raise EvidenceError("Stored evidence hash or identity mismatch")
        return result


def export_atomic(path: Path, value: dict):
    """Publish complete UTF-8 JSON without replacing any existing destination.

    A same-directory hard link is the no-clobber publication point. Local filesystems
    supporting hard links are required. Failure leaves no partial destination.
    """
    fd, temporary = tempfile.mkstemp(prefix=".joinproof-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)


def protect_paths(sources: list[Path], ledger: Path | None, output: Path | None):
    """Reject destinations and SQLite sidecars aliasing sources or each other."""
    protected = [p.resolve() for p in sources]
    destinations = []
    if ledger is not None:
        # SQLite follows a database symlink; protect sidecars beside its target too.
        for location in {ledger.absolute(), ledger.resolve()}:
            destinations.extend(
                Path(str(location) + suffix).resolve()
                for suffix in ("", "-journal", "-wal", "-shm")
            )
        destinations = list(dict.fromkeys(destinations))
    if output is not None:
        destinations.append(output.resolve())
    all_paths = protected + destinations
    for i, path in enumerate(all_paths):
        for j, other in enumerate(all_paths[:i]):
            if i < len(protected) and j < len(protected):
                continue
            if path == other or (path.exists() and other.exists() and path.samefile(other)):
                raise EvidenceError("Evidence destinations must not alias inputs or each other")
