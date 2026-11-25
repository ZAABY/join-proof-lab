"""Read existing ledger evidence without creating or updating a database."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .evidence import EvidenceError, Ledger, export_atomic, protect_paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("run_id", help="Run ID printed by joinproof --ledger")
    parser.add_argument("--output", type=Path, help="Recover verified JSON to a new file")
    args = parser.parse_args(argv)
    reader = object.__new__(Ledger)
    try:
        protect_paths([], args.ledger, args.output)
        uri = args.ledger.resolve().as_uri() + "?mode=ro"
        reader.db = sqlite3.connect(uri, uri=True)
        try:
            if reader.db.execute("SELECT version FROM metadata").fetchall() != [(1,)]:
                raise EvidenceError("Unsupported ledger version")
            result = reader.verify(args.run_id)
        finally:
            reader.close()
        if args.output is not None:
            export_atomic(args.output, result)
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Evidence verification/recovery failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
