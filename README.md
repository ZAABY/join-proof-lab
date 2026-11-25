# Join Proof Lab

A small offline audit for one expensive ETL mistake: joining tables at different grains and then adding up repeated values.

The audit engine, strict input contracts, local evidence ledger, recovery CLI and offline examples are available. A pinned real-data study reproduces 26 populations and 52 SQL/audit plan comparisons. Hosted validation passes on Python 3.10 and 3.12. The deployed evidence report has been checked at phone and desktop widths.

[Read the live evidence report](https://zaaby.github.io/join-proof-lab/report/index.html) · [Browse validation runs](https://github.com/ZAABY/join-proof-lab/actions)

## A total can look right and still be wrong

Two orders are worth 100.00 each. Order A has two event rows; order B has none. An inner join repeats A and drops B. Both the row count and total remain unchanged. Neither check establishes that each order survived once.

Join Proof Lab tracks the number of contributions from each source key. It separates dropped values from repeated values and retains exact failure witnesses. A nonzero gross exposure cannot hide behind a zero net change.

This is an engineering lab, not a new join algorithm or a general proof of business correctness. [Existing research and tools](docs/prior-art.md) address fanout and aggregation consistency. The focus here is a reproducible evidence trail for a deliberately narrow join contract.

Read the [evidence report](report/index.html) for the real-data comparison, per-month results and separate controlled cancellation examples. Open it locally in a browser after cloning; the HTML has no external assets or scripts.

## Run the offline example

Python 3.10 or later and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --extra dev
uv run joinproof examples/cancellation/contract.json
```

The second command prints JSON and exits **2**, intentionally. Its two output rows and total 200.00 match the source, but one order was lost and the other repeated. The result includes `net_cancellation: true` and a failed root-row gate.

An explicit alternative pre-aggregates events to one row per order and uses a left join:

```bash
uv run joinproof examples/preaggregated/contract.json
```

It exits **0**. This is a user-selected plan for preserving the order population. The tool does not silently change an inner join to a left join or decide what missing events should mean.

The runtime uses only the Python standard library. DuckDB is a development/study dependency used as an independent executed-SQL oracle.

Keep results in a local SQLite ledger and export a new JSON file with `--ledger /tmp/joinproof.sqlite --output /tmp/audit.json`. Repeated inputs reuse a deterministic run ID while executions retain separate attempt UUIDs and real timestamps. `uv run joinproof-recover /tmp/joinproof.sqlite RUN_ID` reads and verifies stored evidence without rerunning an audit. See [evidence and recovery](docs/evidence.md) for failure boundaries and limits. Hashes are not a signature or tamper-proof certificate.

## What it checks

- Declared row grain, optionally unique non-null join keys, and required CSV columns.
- Exact output cardinality for a root-key star of ordinary equijoins.
- Exact additive sums in integer minor units, without rounding input values.
- Source, output, dropped and repeated amounts, including signed-error cancellation.
- Per-relation dropped/repeated row counts, bounded key-level witnesses and SHA-256 input/contract fingerprints.
- Explicit conservation gates. Even repeating a zero-valued non-null measure is structurally unsafe.

A passing result only establishes the configured conditions for the bytes read. Turning off a conservation requirement changes what passes. It does not establish that keys identify the same real entity, that the source values are true, or that an allocation is meaningful.

## Supported semantics

Each child joins **directly to the root**, using the same-length tuple of text keys. Left and inner joins can be mixed. Blank keys are SQL NULL and never match. Whitespace is significant. Blank measure values are NULL and ignored by sums; an empty sum is normalized to zero. Money uses an explicit decimal scale, never binary floating point.

Unsupported: arbitrary SQL, post-join filters, key coercion, cyclic joins, chained joins through child columns, inequality/range joins, inferred relationships, automatic deduplication and automatic repair. Read the [contract](docs/contracts.md) and [equations](docs/method.md) before applying it to another dataset.

The implementation groups input rows rather than materializing the wide join. It still reads complete input files and keeps key/grain state in memory. This is not a bounded-memory warehouse engine or a production-scale performance claim.

## Validation

```bash
uv run python -m unittest discover -s tests -v
uv run ruff check src tests
uv run ruff format --check src tests
```

The workflow targets Python 3.10 and 3.12 with synthetic/offline tests only, no Olist download. Both versions pass locally and in the hosted workflow. Each validation run belongs to its reported commit, not every future revision.

The current suite includes 600 seeded cases comparing the factorized result to independently executed DuckDB queries. Cases include empty inputs, duplicate and composite keys, SQL NULL keys, mixed left/inner joins and signed values. A finite test suite is not a proof for every possible input.

## Data and licensing

The [reproducible study](study/README.md) uses the real anonymized [Olist ecommerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce/) from [Olist's own repository](https://github.com/olist/work-at-olist-data/tree/master/datasets). It compares deliberately constructed naive queries with explicit source-grain pre-aggregation. It does not allege that Olist published an incorrect dashboard. Multiple items, payments or reviews for an order are not automatically corrupt records.

Code and synthetic examples: MIT. Olist data and derived study artifacts: **CC BY-NC-SA 4.0**, separately labeled. The code license does not grant commercial use of that dataset or its derived study artifacts. Raw CSVs and review text are not included in this repository. See [DATA_LICENSE.md](DATA_LICENSE.md).

Development is AI-assisted. The test evidence and limits, rather than a claim of unaided authorship, describe what this project establishes.

## Distribution scope

The wheel contains the dependency-free engine and both CLI entry points, not the study, report or example CSVs. Clone the repository or unpack the source distribution to run the documented examples and view the report. No package-registry release is implied by the local build. The source distribution includes the separately licensed Olist aggregate artifacts; the code license does not replace their NC-SA terms.

## Source history

The initial local development files were recovered on 25 November 2026 after local storage loss, before any remote publication. This repository starts from a fresh recovery commit rather than reconstructed or backdated development commits. The study was downloaded from its pinned sources and reproduced twice again, and the tests, distributions and report were checked again after recovery.
