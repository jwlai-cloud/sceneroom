# 003 — Cloud Run, not Agent Engine

**Status:** Accepted · 2026-08-01, confirmed by deployment 2026-08-07

## Context

Agent Engine is the managed path for an ADK agent and needs less deployment
work. Judging runs 2026-09-23 to 10-07 — the service must stay reachable for
about nine weeks after work stops, on a small credit.

## Decision

Deploy the FastAPI app to Cloud Run with `min-instances 0` and
`max-instances 3`.

## Consequences

- **Idle cost is ~$0.** No instance runs between visits; Agent Engine bills
  continuously. This is the difference between the URL being alive in October
  and the credit being gone in September.
- **`max-instances 3` caps the blast radius** of a public URL. It bounds
  concurrency, though not spend — hence the access gate.
- We own the container. That surfaced a real bug: the Dockerfile copied `app/`
  but not `frontend/`, and because the static mount is guarded by
  `FRONTEND.is_dir()` the service started healthy and served 404 at `/`. A
  successful-looking deploy with no product in it. Now covered by
  `tests/unit/test_packaging.py`.
- Long requests are fine: `--timeout 600` comfortably covers a ~30s pass.

## What would make this wrong

If the service needed managed sessions, agent-level tracing, or horizontal
scaling beyond a demo's load, Agent Engine's operational surface would start
paying for itself.
