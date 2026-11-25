# Olist study, reproducible checkpoint

This is our deliberately constructed query experiment, not a claim about Olist's production analytics. Multiple items, payments and reviews per order are not automatically bad data.

## Reproduce

```sh
uv sync --extra dev
uv run python study/reproduce.py /path/to/private/olist-csvs --output /tmp/olist-results.json
```

Put the four original CSVs named in `source-manifest.json` in that directory. If they are missing, add `--download` to explicitly allow retrieval from the manifest's pinned Olist repository URLs. Without that flag, the script has no network step. Every input must match its recorded byte count and SHA-256 before parsing. No raw rows or order-key witnesses are exported. Temporary projected CSVs are removed when the study finishes normally.

The committed aggregate results are in [results/olist.json](results/olist.json). Olist data and these derived results are CC BY-NC-SA 4.0, not MIT. See [../DATA_LICENSE.md](../DATA_LICENSE.md). The reproduction code is MIT.

## Population and independent checks

The full population has 99,441 orders. The 25 nonempty order-purchase months run from September 2016 through October 2018. Child rows follow their order's purchase month, not their own payment, delivery or review date. Counts in the monthly partitions must reconstruct each full source-table count. The script checks and reports child rows without any root order; this pinned dataset has none. No order-status filter is applied.

For each of the 26 populations, two plans are compared:

1. A deliberately naive four-table left join at raw source grain.
2. An explicit plan that groups items, payments and reviews by order before left joining to orders. This chooses an order-level analytical output. Review rows become presence by order; no review score or review text is aggregated or interpreted.

The core predicts cardinality and additive sums from grouped multiplicities. Separately executed DuckDB SQL performs each actual join and aggregation using exact DECIMAL arithmetic. Each raw plan's row count and both sums must equal its core predictions. Each preaggregated plan must pass its declared conservation/root-population gate and match the original selected source sums and independent SQL. That is 52 plan comparisons, plus 600 randomized SQL cases in the test suite.

The preaggregated gate applies to the newly declared aggregated relations. The reproduction script separately checks original source totals so this change of grain cannot silently justify a different amount. It does not certify that order-level aggregation answers a particular business question.

## Full-population result

| Check | Deliberately naive join | Explicit preaggregation |
| --- | ---: | ---: |
| Output rows | 119,143 | 99,441 |
| Item price sum | 14,273,699.65 | 13,591,643.70 |
| Payment sum | 20,579,664.01 | 16,008,872.12 |
| Configured gate | Fail | Pass |

Amounts use the dataset's original monetary units, with two decimal places. They are not converted to euros or current prices. The original item sum is 13,591,643.70 and original payment sum is 16,008,872.12. The raw join repeats contributions from 3,924 item rows and 10,748 payment rows. Source-row counts and repeated output copies are different quantities.

`SUM(DISTINCT payment_value)` on the raw join gives 7,773,585.14, also incorrect: equal amounts from different legitimate payments are not duplicates of the same fact. Distinct-value aggregation is not a general fanout repair.

For 22 of 25 months, the naive plan fails the conservation gate; three sparse months pass. Explicit preaggregation passes all 25. In this positive-valued real dataset, row-count and payment-total checks also catch those same 22 months. We do **not** claim extra detections over those checks in Olist. The controlled [cancellation example](../examples/cancellation/contract.json) demonstrates a different failure mode in which both totals and row count stay unchanged despite loss and repetition. It is synthetic and is never blended into the real-data results.

## Limits

This is one pinned educational dataset and narrow root-key star-join semantics. It is not an estimate of warehouse error prevalence, a benchmark, an arbitrary SQL validator or evidence of adoption. Full CSV bytes and grouping state are held in memory. Download availability can change; pinned hashes define the expected source, not a permanent hosting promise. Review text stays out of the repository and aggregate results.
