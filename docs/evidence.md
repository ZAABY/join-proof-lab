# Evidence ledger and recovery

The audit still works offline without a database. To keep repeatable evidence:

```sh
uv run joinproof examples/cancellation/contract.json --ledger /tmp/joinproof.sqlite --output /tmp/cancellation.json
```

Exit 2 is expected for this deliberately broken join. A completed audit with a failed gate is still useful evidence and is retained. Standard output is the deterministic audit JSON. Standard error prints the run ID and attempt UUID when a ledger is used.

## Two identities

A run ID is SHA-256 over canonical JSON containing engine/schema versions, canonical contract hash, ordered relation names and exact input hashes/byte counts, and witness limit. Identical evidence inputs reuse the run. Changing the witness policy changes the run. The result hash covers the complete deterministic payload. No absolute local paths or wall-clock timestamps enter the result or run ID.

An attempt UUID identifies one execution, with real UTC start/finish timestamps and `running`, `completed` or `failed` state. Repeating a run creates another attempt, not another result. The start is committed before auditing. Result insertion and attempt completion share one SQLite transaction. A process interruption can leave a `running` attempt. It is not treated as success and is not automatically relabeled as failure, since another process might still be working. A fresh execution can complete independently.

## Recover an export

Copy the run ID printed on standard error:

```sh
uv run joinproof-recover /tmp/joinproof.sqlite RUN_ID --output /tmp/recovered.json
```

This opens SQLite read-only, verifies the stored payload hash, recomputes its identity and checks the run ID. It does not re-audit current CSVs or attest that current files are unchanged. To check current data, run a fresh audit. Hashes detect accidental corruption and inconsistent edits, not a malicious editor who rewrites all fields. This is not a signature, trusted timestamp or tamper-proof certificate.

## Output and failure boundaries

An export is written and fsynced to a same-directory temporary file. A hard link atomically publishes the complete bytes without replacing an existing destination; temporary files are removed on ordinary errors. A local filesystem supporting hard links is required. Directory fsync and power-loss durability are not promised. A forced process kill can leave a hidden `.joinproof-*` temporary file, but not a partial published JSON file.

SQLite and filesystem exports are **not** one distributed transaction. The ledger commits first. If an export then fails, the CLI exits 3, prints the retained run ID and explains that evidence remains available for read-only recovery. It does not mark a completed audit as failed merely because the separate export failed. Failed audits record only the exception class, not raw source values. Unrelated SQLite databases and unsupported ledger versions are refused.

The CLI rejects paths and existing hard-link/symlink aliases that would overlap contracts, CSVs, ledger/sidecars or output. Export never overwrites an existing file. This is protection against mistakes in a trusted local directory, not a defense against an attacker concurrently replacing directory entries. Do not run it in an attacker-writable directory.

Exit codes: 0 = completed passing gate; 2 = completed violated gate; 3 = invalid input, ledger or export failure. No network access, source edits, automatic deduplication or repairs occur.

Database symlinks also require checking sidecars beside the resolved target, not only beside the alias. Both sets of destinations are checked. Existing ledgers with incompatible table columns are refused before an attempt is started. These checks still assume a trusted directory and do not lock against concurrent path replacement.
