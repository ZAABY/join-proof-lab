# Prior art and positioning

Join fanout, aggregation consistency, metric grain and factorized aggregation are established topics. Join Proof Lab is not the first tool to detect them, and its multiplication equations are not a new algorithm.

| Source | What it contributes to this project |
| --- | --- |
| [dbt MetricFlow join logic](https://docs.getdbt.com/docs/build/join-logic) | Official documentation shows entity-based restrictions on fanout and chasm joins. This is an existing way to prevent risky joins at the semantic-model layer. |
| [Looker measure troubleshooting](https://cloud.google.com/looker/docs/best-practices/how-to-troubleshoot-when-measures-dont-come-through-a-join) | Official documentation explains the importance of unique non-null primary keys for symmetric aggregates. An audit cannot replace a correct metric model. |
| [Huang, Damalapati and Wu, Aggregation Consistency Errors in Semantic Layers and How to Avoid Them](https://arxiv.org/html/2307.00417v1) | Research discusses duplication, missing values, metric grain, factorized aggregation and user-directed weighting. We use this as prior art and motivation, not as a current feature comparison of BI products. |
| [Practitioner report on grainguard](https://dev.to/rohit9007/i-scanned-1152-dbt-models-for-joins-that-inflate-sum-here-is-what-i-found-1ea) | A public implementation already infers dbt grain and flags risky aggregates without connecting to a database. Its reported survey counts are the author's claims, not independently verified measurements here. |
| [DuckDB EXPLAIN ANALYZE](https://duckdb.org/docs/1.5/guides/meta/explain_analyze) | Official profiling guidance helps distinguish estimated from actual execution. Our correctness oracle uses independently executed SQL results rather than estimated cardinality. |

Sources inspected on 22 November 2026.

## The narrower contribution here

This repository combines declared data-level contracts, exact contribution counts, signed loss/repetition reconciliation, absolute exposure, bounded witnesses, input fingerprints and reproducible experiments. It is intended to make failures explainable and rerunnable on a small local export. It does not infer grain from dbt, replace a semantic layer or optimize arbitrary SQL.

A passing audit answers a restricted mechanical question: do these declared join operations preserve the required row/measure contributions for this input snapshot? It does not answer whether a business allocation is meaningful, whether the data is correct or whether the contract describes the entire production query.
