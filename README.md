# Sceneroom

**An agentic scene room for scripted production — the crew writes the scene,
then holds it to account.**

Built on Google ADK and Gemini, with verification grounded in [Parallel](https://parallel.ai).
Submission for the [Agentic Cinema hackathon](https://agentic-cinema.devpost.com) — **Parallel track**.

---

## The problem

AI-native studios are producing scripted content at a velocity legacy pipelines
can't match — and without the standards & practices department broadcasters
spent decades building. Generated period detail *sounds* right, which is exactly
what makes it dangerous: the errors are introduced by the tooling, not merely
missed by a tired reader.

In June 2026, MBC's *21st Century Grand Princess* drew sustained criticism over
verification errors and historical distortion. The production team and cast
issued public apologies, and scenes were cut from the broadcast — post-air costs
for a pre-air failure.

## What it does

Give it intent — *"night scene, 1963, the detective loses her badge."*

1. The crew **drafts** the scene.
2. It **extracts** every checkable factual, historical, and rights-bearing claim.
3. It **checks canon** — the production bible, for scenes written out of order.
4. It **verifies externally** against the open web through Parallel, keeping the
   sources.
5. It **scans the fandom** — what this audience already tracks and argues about
   — because something can be factually fine and still be a flashpoint.
6. Flags land **inline on the scene**, with citations.
7. Anything it can't adjudicate is marked **contested** and routed to a human.
8. You accept or override; the scene is **revised**, the rationale logged, and
   the corrected scene **re-checked**.
9. One **Imagen** frame closes the loop.

You get a production-ready scene **and its provenance record** — what was
checked, against which source, decided by whom, and why.

## What it deliberately does not do

**It does not guarantee correctness.** Retrieval isn't omniscience, and some
disputes are contested historiography rather than facts to look up — an agent
that ruled on those would be wrong in the most damaging way available.

The promise is narrower and more useful: **no unreviewed claim ships.** Every
claim is either cited and cleared, or explicitly assigned to a person.

It is also not a storyboard tool, a video generator, or a replacement for a
historical consultant.

## Run it

Needs Python 3.11–3.13, [uv](https://docs.astral.sh/uv/), a Google Cloud project
with the Vertex AI API enabled, and a [Parallel](https://parallel.ai) API key.

```bash
git clone https://github.com/jwlai-cloud/sceneroom && cd sceneroom
uv sync

export GOOGLE_CLOUD_PROJECT=your-project        # Vertex AI project
export GOOGLE_CLOUD_LOCATION=global
export GOOGLE_GENAI_USE_VERTEXAI=True
export PARALLEL_API_KEY=your-parallel-key       # without it, checks report unverifiable
gcloud auth application-default login

uv run uvicorn app.fast_api_app:app --port 8080
```

Open <http://localhost:8080>, give the crew a brief, and press **Run the crew**.
`GET /api/health` reports which integrations are live.

Optional:

| Variable | Effect |
|---|---|
| `BIGQUERY_DATASET` | Persist the claims ledger to BigQuery. Unset, it stays in memory. |
| `PARALLEL_PROCESSOR` | `pro` (default in production) or `base`. |
| `SCENEROOM_ACCESS_CODE` | Gate the endpoints that spend money. Unset, the room is open. |
| `SCENEROOM_ESCALATION_CONTACT` | Who contested claims are routed to by name. |

```bash
uv run pytest -q                      # 48 unit tests
uv run python evals/run_eval.py       # 15 claims with known answers
uv run python evals/run_eval.py --compare   # base vs pro
```

### Deploy

```bash
gcloud run deploy sceneroom --source . \
  --min-instances 0 --max-instances 3 --timeout 600 --cpu-boost \
  --service-account sceneroom-run@PROJECT.iam.gserviceaccount.com \
  --set-secrets PARALLEL_API_KEY=parallel-api-key:latest
```

`min-instances 0` idles at ~$0. Full walkthrough, including the least-privilege
service account and the BigQuery dataset ACL, is in
[`docs/TUTORIAL.md`](docs/TUTORIAL.md).

### Where the integrations actually live

| | |
|---|---|
| Parallel Search API | [`app/services/parallel_client.py`](app/services/parallel_client.py) — called by the Verifier and Rights checks |
| Parallel MCP server | [`app/services/parallel_mcp.py`](app/services/parallel_mcp.py) — `web_search` / `web_fetch`, given to the Fandom agent only |
| Gemini on Vertex AI | [`app/agents/`](app/agents/) — seven `LlmAgent`s, `google-adk` 2.6.1 |
| ADK graph workflows | [`app/agents/check_graph.py`](app/agents/check_graph.py), [`revise_workflow.py`](app/agents/revise_workflow.py) |
| BigQuery ledger | [`app/services/ledger.py`](app/services/ledger.py) — append-only |
| Imagen / Gemini image | [`app/services/frame.py`](app/services/frame.py) |

## Status

Early. See [`docs/PRD.md`](docs/PRD.md) for the full spec and
[`CLAUDE.md`](CLAUDE.md) for build conventions.

## License

[Apache 2.0](LICENSE).
