# Arithmetic and its boundary

Consider a root relation R and children C1 through Cn. Every ON clause compares one child's key tuple to R's key tuple with ordinary SQL equality. Children are not joined through one another.

For a matching non-null key k, let r(k) be the number of root rows and cj(k) the number of rows in child j. Define fj(k) as:

- Left join: max(cj(k), 1).
- Inner join: cj(k).

For a root key containing a NULL, every cj(k) is zero, even when the child also contains a NULL key. This is the behavior of SQL `=`, not `IS NOT DISTINCT FROM`.

The output row count is:

```text
sum over root key groups k: r(k) * product over children j of fj(k)
```

Each root source row contributes `product(fj(k))` times. Each row of a matching child i contributes:

```text
r(k) * product over other children j != i of fj(k)
```

A child row with no matching root, including a NULL key, contributes zero times. A zero factor from an inner sibling also removes the child row's contribution. An absent left-joined child contributes a SQL NULL placeholder, not a synthetic non-null measure row.

These equations avoid constructing the potentially large wide join. The current Python implementation uses a straightforward product per child, so the factor computation is quadratic in the number of children per root key. The contract caps the number of relations at 32. Reading and grouping the input files, keeping optional grain sets and retaining bounded witnesses still costs memory and time. No speedup is promised for a small or already selective join.

## Exact reconciliation

For source measure values vi and computed contribution multiplicities mi:

```text
source   = sum(vi)
output   = sum(vi * mi)
lost     = sum(vi for mi == 0)
repeated = sum(vi * (mi - 1) for mi > 1)
delta    = output - source = repeated - lost
exposure = sum(abs(vi) * abs(mi - 1))
```

Amounts are signed. `lost` and `repeated` can be negative for signed measures; they are not absolute error magnitudes. `exposure` is an absolute source-contribution measure, not an estimate of economic loss. It can reveal cancellations in a zero net delta.

SQL NULL measure values do not enter the sum. Their source rows remain visible in relation-level counts. Empty sums are normalized to zero in both the core and its independent SQL tests. Multiplicity safety is stricter than equality of totals: every non-null source measure row must have mi = 1, including zero-valued rows. This does not assert that the measure is additive over every possible dimension or that the source values are correct.

## Witnesses

An affected relation-key group records the key tuple, source row count, copies per source row, output contributions and grouped source measure units. The group is sufficient to explain its contribution count under this star model. Witness selection ranks affected groups by absolute measure exposure, then row exposure and a deterministic tie-breaker. It is not a minimum-cardinality SQL counterexample or a causal proof about business semantics.

## Validation, not universal proof

Tests compare against separately materialized/executed DuckDB joins on bounded seeded examples. They include composite keys, SQL NULLs, empty relations, multiple children, duplicate roots, positive/negative/zero/NULL measures and mixed left/inner joins. Targeted tests show a row count and grand total can both match while different source rows are dropped and repeated.

Nothing in this model covers post-join predicates, range conditions, casts, transformations of join keys, cyclic graphs, joins from a child key, floating-point aggregation, medians or arbitrary SQL. A contract that omits part of an actual query is not a certificate for that query.
