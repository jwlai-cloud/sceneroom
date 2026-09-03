# Progress

_Deadline **2026-09-07 14:00 PT**. Judging **2026-09-23 → 10-07**, so the URL
must survive into October._

**Live:** <https://sceneroom-320877670799.us-central1.run.app> · access code is
on the submission page · revision `sceneroom-00021-244`

## Done

| | Evidence |
|---|---|
| Cloud Run deployment, scale-to-zero | `min-instances 0`, `max-instances 3`, `--timeout 600` |
| Seven-agent crew | writer/reviser, extractor, continuity, verifier, fandom, rights, adjudicator |
| Deterministic escalation | `route()` is a pure function; 6 tests |
| Streamed runs | SSE, real per-agent timings, ~30s pass |
| Console UI | inline flags, claim↔note bridge, 3 themes, contested lane |
| **Parallel Search API** | Verifier + Rights, orchestrator-retrieved |
| **Parallel MCP** | Fandom agent searches for itself |
| **BigQuery ledger** | `agent-era.sceneroom.{claims_ledger,scenes}`, append-only |
| Secret Manager + least privilege | no key material in the container; dataset-scoped WRITER |
| Access gate | cookie-based, guards the five endpoints that spend money |
| One payoff frame | `gemini-3.1-flash-image`, only once nothing is open |
| Tests | 48 unit, ruff clean |
| Docs | `ARCHITECTURE.md`, 7 ADRs, `SUBMISSION.md`, `VIDEO.md` |
| Devpost thumbnail | `docs/sceneroom-thumbnail.jpg`, 1200×800 |
| Teaching artefact | `tutorial.html` — navigable page, + `TUTORIAL.md` |
| Diagrams | topology + handshake sequence, both 9/9 showcase checks |
| Revise graph | ✅ ADK `Workflow` — reviser → critic → route, retry once |
| Check graph | ✅ ADK `Workflow` — one dynamic node fans out over however many claims |
| ADK / scaffold | ✅ 2.6.1, migrated to `agents-cli-manifest.yaml` |
| Demo video | ✅ 2:54 — cold open states the edge, the pass, and how Parallel is used |
| Recent scenes + record export | reopen past work; download the provenance record |
| Continuity actually fires | the bible example produces canon claims |

Verified by driving the deployed page in a browser, not by reading code: a live
run streams all seven agents, produces cited verdicts including `contradicted`
and `contested`, records the decision to BigQuery, and renders the frame.

## Left

**Nothing in the PRD scope line is unbuilt.** Every item — drafting, extraction,
continuity against a bible, Parallel verification with citations, four-way
classification, inline flags, accept/override with logged rationale, the revise
and re-check loop, the BigQuery ledger, contested escalation, one payoff frame,
a deployed URL — is live and verified in a browser against the deployment.

What remains is not code:

| | Owner | Notes |
|---|---|---|
| **Video notes** | you | v3 plays; you said small feedback is coming. Three commands rebuild it. |
| **Submit to Devpost** | you | `docs/SUBMISSION.md` is written. Access code is in it. |
| **PR `dev` → `master`** | either | master is protected and 32 commits behind. |
| Keep the URL alive to Oct 7 | — | Cloud Run idles at ~$0; nothing to do unless it breaks. |

Optional, in the order I would take them if there is time:

1. **A second demo scene** that reliably produces a `contested` verdict, so the
   video's strongest beat is not left to chance.
2. **Widen the eval** past 15 claims, and wire `eval compare` between runs so a
   prompt change cannot regress a case silently.
3. **Multi-scene continuity** — the Continuity agent already checks a bible;
   checking scene 12 against scenes 1–11 is the obvious v2 and is filed under
   "what's next" in the submission, not built.

## What is deliberately not being built

Recorded so it stops being re-proposed:

- **A storyboard.** One frame, no grid, no variants. Image generation is the
  crowded lane.
- **Multi-scene storybook / scene management / plot tools.** The scope line is
  one scene, not a screenplay. This is the failure mode that eats the remaining
  time.
- **Video generation.** Out since the PRD.

Good v2 ideas, filed for "What's next" rather than built: multi-scene
continuity (the Continuity agent already checks a bible; checking scene 12
against scenes 1–11 is the obvious next step), and house-style skills a
standards desk could add without forking.

## Traps this project has already paid for

1. `GOOGLE_APPLICATION_CREDENTIALS` in the shell profile points at a
   TrafficGuard key and overrides ADC — local runs silently bill the wrong
   project. Use `env -u GOOGLE_APPLICATION_CREDENTIALS`.
2. The Dockerfile copied `app/` but not `frontend/`. The static mount is guarded
   by `FRONTEND.is_dir()`, so the container started healthy and served 404 at
   `/` — a successful-looking deploy with no product in it.
3. `/api/scenes/stream` was shadowed by `/api/scenes/{scene_id}` and 404'd as
   "No such scene".
4. `mcp` 2.x moved `mcp.shared.session`; ADK imports it, catches the
   ImportError, and logs at debug — the MCP toolset vanishes silently. Pinned
   `<2.0`.
5. `imagen-*` publisher models are not available to this project in any region
   tried, and `generate_images` is deprecated. Listing the models the project
   can actually see was the only reliable way to find that out.
6. Scenes lived only in the instance that drafted them, so a decision could 404
   on another instance. Fixed by persisting scenes to BigQuery.
7. Production ran `PARALLEL_PROCESSOR=pro`. Re-running the eval the day before
   submission showed pro had drifted back to **1 wrong call** — on `sejong-veto`,
   a live historiographical dispute, which rule 4 forbids outright. Switched to
   `base`: 9/15, 6 missed, **0 wrong**. The eval was the only thing that caught it.
8. `gcloud` CLI user credentials went stale while ADC stayed valid — every
   command failed `PERMISSION_DENIED` on a project the account owns. Workaround:
   `CLOUDSDK_AUTH_ACCESS_TOKEN=$(gcloud auth application-default print-access-token)`.

Every one was found by running the thing, not by reading about it.
