# Kickoff — continuing the build

```bash
cd /Users/junwei.lai/Projects/Agent/sceneroom && claude
```

`CLAUDE.md` loads automatically. Paste the prompt below as the first message.

---

## Where the build actually is (2026-08-07)

**Deployed and public:** <https://sceneroom-320877670799.us-central1.run.app>
Cloud Run, project `agent-era`, `min-instances 0` so it idles at ~$0 and
`max-instances 3` so a public URL cannot run up a Gemini bill.

| Piece | State |
|---|---|
| Agents — writer, reviser, extractor, **continuity**, verifier, fandom, **rights**, **adjudicator** | ✅ `app/agents/` |
| Workflow — draft → extract → check → adjudicate → decide → revise → re-check | ✅ `app/orchestrator.py` |
| Run streaming — per-agent events over SSE | ✅ `app/services/runs.py`, `/api/stream/scene` |
| UI — production console, inline flags, contested lane, ledger strip | ✅ `frontend/` |
| **Deployed hosted URL** | ✅ Cloud Run, least-privilege SA `sceneroom-run@agent-era` |
| Parallel integration | ⚠️ Search API coded, **running on offline fixtures — no API key yet** |
| Parallel **MCP server** | ❌ not built — PRD §4 calls for MCP *and* Search. Blocked on the key |
| Claims ledger | ⚠️ in-memory; BigQuery implemented behind the same Protocol, switches on `BIGQUERY_DATASET` |
| Tests | ✅ 17 unit passing, ruff clean |
| Imagen payoff frame | ❌ not started (`ENABLE_IMAGE` flag exists, unused) |
| Demo video + Devpost write-up | ❌ not started |
| `ARCHITECTURE.md`, ADRs, `PROGRESS.md` | ❌ not written — `hackathon-engineering` asks for these |

Verified rather than assumed, by driving the deployed page in a real browser:
a live run streams all seven agents with real timings, the pinned demo scene
produces two sourced contradictions plus a rights-clearance finding, and
"Keep — deliberate" leaves the scene text untouched while recording the
rationale in the ledger. No console errors.

### One blocker, needing the human

**`PARALLEL_API_KEY`** — sign up at <https://platform.parallel.ai>. Everything
runs on offline fixtures until then, and the UI says so in the top bar. This is
a *scored, mandatory* requirement and it also gates the MCP server work, so it
is the highest-value outstanding item by a distance.

### Traps this project has already fallen into

- `GOOGLE_APPLICATION_CREDENTIALS` is exported in the shell profile pointing at
  a TrafficGuard service-account key. It overrides ADC, so local runs silently
  bill `tgds-dev`. Run local commands with `env -u GOOGLE_APPLICATION_CREDENTIALS`.
- The `Dockerfile` copied `app/` but not `frontend/`. Because the static mount
  is guarded by `FRONTEND.is_dir()`, the container started healthy and served
  404 at `/` — a successful-looking deploy with no product in it. Guarded now by
  `tests/unit/test_packaging.py`.
- `/api/scenes/stream` was shadowed by `/api/scenes/{scene_id}` and 404'd as
  "No such scene." Stream routes live under `/api/stream/` and
  `tests/unit/test_routes.py` fails if a wildcard shadows one.

---

## The prompt

> Read `CLAUDE.md` and `docs/PRD.md` first — they hold decisions already made
> under adversarial review. Don't re-litigate them; if you think one is wrong,
> say so in a sentence and continue. Then read the "Where the build actually is"
> section of `docs/KICKOFF.md`.
>
> **Context.** Sceneroom is an agentic scene room for scripted production: the
> crew drafts a scene from the writer's intent, extracts every checkable claim,
> checks it against fact and against what this audience already litigates (both
> via Parallel), surfaces flags inline on the page, and on the writer's decision
> either fixes and re-checks, records it as deliberate artistic licence, or
> escalates it — leaving a provenance record. Agentic Cinema hackathon,
> **Parallel track**, deadline **2026-09-07 14:00 PT**, judged **Sep 23 – Oct 7**
> so the deployment must survive into October.
>
> The core loop is already built, tested and pushed. Do not rebuild it.
>
> **Priorities, in order:**
> 1. **Deploy to Cloud Run** and get a live public URL. Cloud Run specifically,
>    not Agent Engine — Cloud Run idles at ~$0 and the service must stay up for
>    ~9 weeks on a $100 credit. This is the single most overdue item.
> 2. **Wire the real Parallel key** via Secret Manager once available, and
>    confirm live verification end to end.
> 3. **Swap the ledger to BigQuery** (`BIGQUERY_DATASET`) so the audit trail is
>    durable — this is what satisfies the "updating dynamic databases"
>    production goal.
> 4. **One Imagen payoff frame** of the corrected scene. Cut it if it threatens
>    the timeline.
> 5. **3-minute video** (budget two full days) and the Devpost write-up. The
>    video is pre-recorded; the hosted URL stays live separately for judges.
>
> **Use these skills:** `hackathon-engineering` (keep `docs/ARCHITECTURE.md`,
> ADRs and a progress log current), `google-agents-cli-deploy` (Cloud Run),
> `google-agents-cli-adk-code` (ADK patterns), `frontend-design` (UI work),
> `hackathon-demo-video` and `hackathon-submission` at the end.
>
> **Verify, don't trust.** Check APIs against the installed package or official
> docs. Cheatsheets have been wrong three times on this project: the ADK 2.5
> graph edge API is a `{route: target}` dict not a 3-tuple;
> `google.adk.skills.load_skills_from_dir` doesn't exist; and the demo button
> bug was only caught by driving the real page with Playwright, not by testing
> the API. Run the UI in a browser before believing it works.
>
> **Housekeeping.** No `Co-Authored-By` trailers. One runnable check for
> non-trivial logic, no heavy test ceremony.
>
> **Start by** running the app locally, confirming the loop still works, then
> proposing the deployment plan. Wait for my go before deploying.

---

## Running it

```bash
uv sync
uv run --with pytest pytest tests/unit -q          # 17 tests
uv run --with ruff ruff check app tests

# -u GOOGLE_APPLICATION_CREDENTIALS matters: the shell profile exports a
# TrafficGuard service-account key that overrides ADC and bills the wrong project.
env -u GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT=agent-era \
  uv run uvicorn app.fast_api_app:app --port 8080   # then open http://localhost:8080
```

Redeploy:

```bash
gcloud run deploy sceneroom --source . --project agent-era --region us-central1 \
  --service-account sceneroom-run@agent-era.iam.gserviceaccount.com \
  --allow-unauthenticated --min-instances 0 --max-instances 3 \
  --timeout 600 --cpu-boost --memory 1Gi \
  --set-env-vars GOOGLE_CLOUD_PROJECT=agent-era,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=True
```

`/api/health` reports whether Parallel is live and which ledger backend is
active — check it first when something looks wrong.
