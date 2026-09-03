# 001 — Agents have no tools; the orchestrator retrieves

**Status:** Accepted · 2026-08-07

## Context

Every agent needs evidence. The obvious build is to give each one a search tool
and let it look things up — it is fewer moving parts and it is what most agent
frameworks demonstrate.

The product's claim is narrower than "accurate": *no unreviewed claim ships*,
and every verdict is grounded in a citation a studio could produce later during
a controversy. That claim collapses if a citation can be invented.

## Decision

No agent holds a retrieval tool. `app/orchestrator.py` calls Parallel and pastes
the returned sources into the agent's prompt. The Verifier's instruction says it
outright: *"You do not use prior knowledge as evidence — only what the sources
say."*

## Consequences

- **A citation cannot be hallucinated.** Every URL in the UI came out of a
  Parallel response, not out of a model.
- **The pipeline is deterministic** — control flow, not a model choosing a next
  step. This is also what the hackathon brief asks a multi-step agent to show.
- **"No sources" stays honest.** `_check_factual` returns `unverifiable` before
  any model call, so absence of evidence never reaches a model that might
  rationalise it into support. A measured consequence: on a scene where the
  fixtures matched nothing, the Verifier ran in ~0.0s and made zero model calls.
- **Cost:** the orchestrator must know what to search for. A model that searches
  can chase a lead it notices mid-answer; ours cannot. See ADR 004 for the one
  place that mattered enough to make an exception.

## What would make this wrong

If verdict quality turned out to be limited by the *breadth* of retrieval rather
than the *quality* of judgement, tool-using verification would be worth
re-testing — with an eval set, not by feel.
