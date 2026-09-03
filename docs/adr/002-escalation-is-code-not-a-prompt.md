# 002 — The escalation rule is a pure function, not a prompt

**Status:** Accepted · 2026-08-07

## Context

`CLAUDE.md` sets a hard product rule: contested history is never adjudicated by
the agent; it goes to a named human. The natural implementation is an
Adjudicator agent instructed to escalate contested claims.

A guarantee implemented as a prompt is not a guarantee. It drifts with model
versions, it can be argued out of by a persuasive context, and it cannot be
tested except by sampling.

## Decision

Split the Adjudicator:

- **Routing is `route()`** in `app/agents/adjudicator.py` — pure, total, and
  unit-tested. Same claim, same mode, same answer, every time.
- **The model writes only the handoff note** for the person picking the claim
  up, and is instructed to state the competing positions without saying which
  is right.

## Consequences

- The guarantee is a test (`tests/unit/test_adjudicator.py`), not a hope.
  `contested` escalates in both production modes; `unverifiable` escalates in
  documentary and not in fiction; every route returns a non-empty human-readable
  reason.
- The UI can trust it. The flag counter and the decision buttons both read
  `needs_human` from the Adjudicator rather than re-deriving a second rule in
  the browser — an earlier version did exactly that and demanded decisions on
  claims the backend had already cleared.
- Mode is one branch in one function, so "same engine, different threshold" is
  literally true rather than a slogan.

## What would make this wrong

Nothing about model capability. This is a governance property, not a quality
one — it should survive better models.
