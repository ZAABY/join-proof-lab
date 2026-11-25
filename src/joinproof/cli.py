"""Offline JSON audit command. No network calls or source-data writes."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .contracts import ContractError, load_contract
from .engine import audit
from .evidence import Ledger, export_atomic, protect_paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "contract", type=Path, help="Version 1 JSON contract next to its CSV inputs"
    )
    parser.add_argument("--witness-limit", type=int, default=12)
    parser.add_argument("--ledger", type=Path, help="Optional local SQLite evidence ledger")
    parser.add_argument("--output", type=Path, help="Export JSON to a new file, never overwrite")
    args = parser.parse_args(argv)
    ledger = attempt = None
    completed = False
    try:
        contract = load_contract(args.contract)
        protect_paths(
            [args.contract, *(r.path for r in contract.relations)], args.ledger, args.output
        )
        if args.output is not None and args.output.exists():
            raise ValueError("Output already exists; choose a new path")
        if args.ledger is not None:
            ledger = Ledger(args.ledger)
            attempt = ledger.start()
        result = audit(contract, args.witness_limit)
        if ledger is not None:
            run_id = ledger.complete(attempt, result)
            completed = True
            print(f"Evidence run {run_id}; attempt {attempt}", file=sys.stderr)
        if args.output is not None:
            export_atomic(args.output, result)
    except (ContractError, ValueError, OSError, sqlite3.Error) as exc:
        if ledger is not None and attempt is not None and not completed:
            try:
                ledger.fail(attempt, type(exc).__name__)
            except (ValueError, sqlite3.Error) as failure:
                print(f"Attempt recovery needed: {type(failure).__name__}", file=sys.stderr)
        prefix = (
            "Export failed; ledger evidence retained"
            if completed
            else "Invalid audit input/evidence"
        )
        print(f"{prefix}: {exc}", file=sys.stderr)
        return 3
    finally:
        if ledger is not None:
            ledger.close()
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
