# Declared contracts

Version 1 supports CSV files and a root-key star join. Every field is explicit. Unknown fields are errors, not silently ignored settings.

Each contract has:

- `version`: integer 1.
- `preserve_root_rows`: boolean. If true, each root row must contribute exactly once, even when the final row count happens to match.
- `relations`: ordered nonempty list, root first, at most 32 entries.

Each relation has:

| Field | Meaning |
| --- | --- |
| `name` | Unique relation label, no period. |
| `path` | CSV path within the contract directory. Resolved symlinks cannot escape that directory. |
| `key` | Nonempty list of CSV columns. Each child tuple matches the root tuple position by position. |
| `grain` | Columns asserted to identify source rows. Duplicates and blanks fail. An empty list means no grain assertion, not a claim that rows are unique. |
| `join` | `root` for the first relation, otherwise `left` or `inner`. |
| `key_unique` | If true, the join tuple must be unique and non-null in this relation. False permits repeated keys; it does not certify that they are intended. |
| `measures` | List of additive fixed-point columns to track. May be empty. |

Each measure declares `name`, `column`, integer `scale` from 0 to 9, and boolean `conserve`. The pair `(relation name, measure name)` identifies a metric. If conservation is required, every non-null source measure row must contribute exactly once. A repeated zero fails; a dropped NULL does not fail this metric gate, although row/grain gates can still fail.

## No implicit repairs

Repeated child keys are a normal feature of event tables. A join is not automatically wrong because it fans out. Conversely, a unique-key check does not tell you whether two different key encodings represent the same entity. The contract must match the intended population and metric grain.

The engine reports orphan child rows even when there is no gate for them. If those rows carry a conserved measure, dropping them fails that measure gate. There is no implicit referential-integrity gate for a dimension with no measures.

Do not disable a requirement merely to make a CI run green. If duplication or population loss is intentional, document why the alternative contract is the one you want.

## Parsing details

CSV keys are text. Leading zeroes survive. Empty strings become NULL; the literal text `NULL` is an ordinary key. Spaces are not trimmed, case is not folded, and types are not coerced. Ragged records, repeated header names and missing required columns are errors. Extra columns are ignored for arithmetic but remain part of the input byte hash.

Measures accept finite, fixed-point ASCII decimal strings, not scientific notation or NaN. Values must fit the declared scale without rounding. Extra trailing fractional zeroes are allowed. Blank means NULL. A scale of 2 stores 12.34 as 1234 integer minor units. There is no currency conversion, currency inference, or assertion that all measures share a currency.

Source snapshots are read-only. Each file is read once into bytes, hashed and parsed from those same bytes. Files are not a cross-file transaction: independently changing upstream files can yield an inconsistent set even if each hash is accurate. Stage an immutable export first. Later provenance can identify the bytes but cannot certify upstream snapshot consistency.

## Exit codes

The CLI writes one result object to standard output. It returns 0 for passing declared gates, 2 for a completed audit with contract violations, and 3 for invalid audit inputs. Argument-parser usage errors return 2, following Python argparse conventions; CI integrations should inspect the JSON when they need to distinguish usage errors from failed gates.

Witnesses are diagnostic samples, not the complete failure set. `witness_count` is the number of affected relation-key groups; `witness_limit` bounds the retained list. Keys can be sensitive in your own data. Keep audit outputs within the same access boundary as the inputs.
