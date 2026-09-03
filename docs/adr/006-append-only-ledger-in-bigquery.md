# 006 — An append-only BigQuery ledger, holding scenes too

**Status:** Accepted · 2026-08-07

## Context

The ledger is the product: a provenance record a studio can produce when a
controversy lands. Session state would have been enough for a demo and is
explicitly called out as a toy in `CLAUDE.md`.

While swapping it, a real bug surfaced. `save_scene` was inherited from the
in-memory implementation, so scenes lived only in the process that drafted them.

## Decision

Two append-only BigQuery tables, `claims_ledger` and `scenes`, written on every
change. Memory is a read cache in front of them; a cache miss falls back to a
query. Enabled by `BIGQUERY_DATASET`; unset keeps the in-memory ledger for local
work and tests.

## Consequences

- **Decisions survive Cloud Run.** Requests route independently across
  instances, so a writer could draft on one instance and land their decision on
  another and get "No such scene" — a lost decision that reads as a missing
  record. Only visible under concurrent load, i.e. exactly during judging.
- **Append-only, deliberately.** A record you can edit is not provenance. A
  scene's current state is its most recent snapshot; warming the cache after a
  read-back must not re-append, or every read would rewrite history.
- The scene is stored whole as JSON rather than shredded into columns. The model
  still moves, and a migration that loses provenance is worse than a column we
  cannot `GROUP BY`.
- A failed audit write logs and continues, so an unreachable warehouse cannot
  block a writer from deciding. The row is then missing from the ledger — that
  is a known gap, not a guarantee. The scene keeps the decision; the provenance
  record is what degrades.
- Least privilege held: the runtime account has `WRITER` on the one dataset and
  `jobUser` at project level, so it cannot create datasets — `_ensure_dataset`
  tolerates being refused rather than demanding project-wide rights for a call
  that succeeds once and is denied every day after.
