# 005 — Stream runs over SSE, not a polled registry

**Status:** Accepted · 2026-08-07

## Context

A full pass takes ~30s, measured. The UI showed one unchanging sentence for all
of it, which reads as a hang — and hid the only moment the system is visibly
multi-step, which is precisely what the hackathon brief asks to see.

Two ways to surface progress: a run registry the client polls, or a streamed
connection.

## Decision

Server-sent events. `GET /api/stream/scene` emits a `crew` event, then a `step`
event per agent transition, then the finished `scene`.

## Consequences

- **No shared state.** Polling needs a run store, and Cloud Run routes each poll
  independently across instances, so a poll would often land on an instance that
  never saw the run. One streamed connection stays with the instance doing the
  work.
- The wait became the evidence: `Writer 00:09 — drafted 1220 characters`,
  `Extractor 00:12 — 8 checkable claims`, `Continuity — no canon claims in this
  scene`. Real timings, real findings, nothing simulated.
- `EventSource` cannot set headers, which decided two later designs: the brief
  travels as query parameters, and the access gate is a cookie rather than a
  header or a query parameter.
- A dropped connection loses the timeline, not the work — the orchestrator keeps
  running and the scene still lands in the ledger.

## Trap recorded

`/api/scenes/stream` was shadowed by `/api/scenes/{scene_id}`, declared earlier,
and 404'd as "No such scene" — a routing bug wearing the costume of a missing
record. Stream routes live under `/api/stream/` and `tests/unit/test_routes.py`
fails if any wildcard shadows one.
