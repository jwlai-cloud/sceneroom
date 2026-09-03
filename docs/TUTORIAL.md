# How Sceneroom was built

A walk through the decisions, with links to the primary sources for each. Read
this if you want to build something similar — or if you want to know which of
our choices you should copy and which you should not.

Every link goes to the actual documentation we used, not a summary of it. Where
a doc was wrong or out of date, that is noted, because that happened five times.

**Read this as a page:** [`tutorial.html`](tutorial.html) — navigable, with the
diagrams linked inline.

**Live:** <https://sceneroom-320877670799.us-central1.run.app> ·
**Topology:** [`sceneroom-agents.html`](sceneroom-agents.html) ·
**One pass:** [`sceneroom-run.html`](sceneroom-run.html) ·
**Decisions:** [`adr/`](adr/)

---

## 0. What it does, in one paragraph

A writer gives an intent. Seven Gemini agents draft a scene, extract every
checkable claim, check each against the production bible and the open web,
and classify it `verified` / `contradicted` / `contested` / `unverifiable`.
Claims needing a human are routed by a pure function. The writer chooses **fix**,
**keep — deliberate**, or **escalate**, and the choice plus its rationale and
sources is appended to BigQuery. One generated frame closes the loop.

---

## 1. Agents: `LlmAgent` with a schema, not a chat loop

Every agent is a single-turn ADK `LlmAgent` with an `output_schema`. No tool
loop, no retries, no conversation.

```python
from google.adk.agents import LlmAgent

def build_verifier() -> LlmAgent:
    return LlmAgent(
        name="verifier",
        model=MODEL,                    # gemini-flash-latest
        instruction=VERIFIER_INSTRUCTION,
        output_schema=VerificationResult,   # a pydantic model
        output_key="verification",
    )
```

`output_schema` forces structured JSON, so downstream code never parses prose.

- **ADK agents:** <https://adk.dev/agents/>
- **LlmAgent reference:** <https://adk.dev/agents/llm-agents/>
- Source: [`app/agents/verifier.py`](../app/agents/verifier.py)

> **Worth knowing:** ADK 2.5+ supports `output_schema` **together with** `tools`
> — tools run during the thought loop, structure is enforced on the final
> answer. Older guidance says these are mutually exclusive. Check the installed
> package, not a blog post.

### Running one

```python
runner = InMemoryRunner(agent=agent, app_name="sceneroom")
await runner.session_service.create_session(...)
async for event in runner.run_async(user_id=..., session_id=..., new_message=msg):
    ...
```

- **Runtime & runners:** <https://adk.dev/runtime/>
- Source: [`app/services/runner.py`](../app/services/runner.py)

---

## 2. The decision that shaped everything: agents hold no tools

Retrieval lives in Python. The orchestrator calls Parallel and pastes the
sources into the agent's prompt. The Verifier is told outright: *"You do not use
prior knowledge as evidence — only what the sources say."*

Three consequences:

1. **A citation cannot be hallucinated** — every URL came out of an API
   response, not a model.
2. **The pipeline is deterministic** — control flow, not a model choosing a next
   step.
3. **"No sources" stays honest** — the code short-circuits to `unverifiable`
   *before* any model call.

The cost: the orchestrator has to know what to search for. A tool-using agent
can chase a lead it notices mid-answer; ours cannot.

→ [ADR 001](adr/001-agents-have-no-tools.md)

**Copy this if** your product's claim is about provenance. **Don't** if you need
open-ended research — see the one exception below.

---

## 3. MCP, for exactly one agent

The Fandom agent asks *what has this audience already litigated?* That is
iterative — spot a controversy, read what the objection was, trace what it cost.
One fixed query answers a shallower question. So it gets Parallel's MCP server.

```python
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams

MCPToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://search.parallel.ai/mcp",
        headers={"Authorization": f"Bearer {key}"},
    ),
    tool_filter=["web_search", "web_fetch"],
)
```

- **ADK + MCP:** <https://adk.dev/tools/mcp-tools/>
- **Parallel Search MCP:** <https://docs.parallel.ai/integrations/mcp/search-mcp>
- **Model Context Protocol:** <https://modelcontextprotocol.io/>
- Source: [`app/services/parallel_mcp.py`](../app/services/parallel_mcp.py)

> **Trap that cost an hour.** `mcp` 2.x moved `mcp.shared.session`, which ADK
> imports. Install plain `mcp` and you get 2.x, ADK catches the `ImportError`,
> **logs it at debug**, and the toolset silently disappears. Pin `mcp<2.0`.

→ [ADR 004](adr/004-mcp-for-one-agent-only.md)

---

## 4. Where a graph beats a loop

Choosing **fix it** used to accept any non-empty rewrite. A revision that
changed the wording but not the fact sailed into another 30-second round of live
checking. So the fix path became revise → judge → maybe retry.

We built it twice. First as a `LoopAgent`, then as an ADK **`Workflow` graph**:

```python
from google.adk import Agent, Event, Workflow

def route(node_input) -> Event:
    return Event(route=[decide_route(result, node_input)])   # a pure function

Workflow(
    name="revise_until_fixed",
    edges=[
        ("START", prepare, reviser, stash, critic, route),
        (route, {"retry": prepare, "done": finish}),
    ],
)
```

Edges are **tuple chains**; a `dict` inside a chain is a routing map. `"START"`
is a string. A node routes by emitting `Event(route=[...])`, matched **exactly**
against edge keys.

- **Graph workflows:** <https://adk.dev/graphs/>
- **Data between nodes:** <https://adk.dev/graphs/data-handling/>
- **Prebuilt workflow agents:** <https://adk.dev/agents/workflow-agents/>
- Source: [`app/agents/revise_workflow.py`](../app/agents/revise_workflow.py)

**Why the graph won**, and it is not the deprecation warning: the routing
decision becomes a plain function. The docs describe the graph API as
*"switching between non-deterministic AI-powered agents and deterministic code
as needed"* — that is the whole argument. `LoopAgent` terminates on `escalate`,
set from inside a tool on the model's own agent, so the decision to stop lived
with the model.

> **Two traps.** (1) An `LlmAgent` used as a node runs `single_turn` with
> `include_contents='none'` — it does **not** see the conversation; input arrives
> as `node_input`. (2) Route keys match exactly: our model answered `"Not Fixed"`
> against a `"not_fixed"` edge, nothing matched, and the branch ended silently.
> Normalise the key **in code**, never by asking the prompt nicely.

→ [ADR 007](adr/007-workflow-graph-over-loopagent.md)

---

## 5. The guarantee that is code, not a prompt

The product's hard rule: contested history always reaches a human. That is a
pure function, not an instruction.

```python
def route(claim: Claim, mode: Mode) -> tuple[bool, str]:
    if claim.verdict == Verdict.CONTESTED:
        return True, "Sources actively disagree. This system does not adjudicate disputes."
    ...
```

A guarantee implemented as a prompt drifts with model versions, can be argued
out of, and cannot be tested except by sampling. This one has six tests.

→ [ADR 002](adr/002-escalation-is-code-not-a-prompt.md) ·
Source: [`app/agents/adjudicator.py`](../app/agents/adjudicator.py)

**This is the transferable idea.** If your agent has one property you'd be
embarrassed to get wrong, implement it in code and test it. Everything else can
be a prompt.

---

## 6. Streaming the wait, because the wait is the product

A pass takes ~30s, measured. The UI showed one unchanging sentence for all of
it, which reads as a hang and hides the only moment the system is visibly
multi-step.

Server-sent events, not polling — polling needs shared state, and Cloud Run
spreads polls across instances, so a poll often lands on an instance that never
saw the run.

```python
return StreamingResponse(events(), media_type="text/event-stream",
                         headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

- **FastAPI streaming:** <https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse>
- **EventSource:** <https://developer.mozilla.org/en-US/docs/Web/API/EventSource>
- Source: [`app/services/runs.py`](../app/services/runs.py), [`app/fast_api_app.py`](../app/fast_api_app.py)

> `EventSource` can only issue **GET** and cannot set headers. That decided two
> later designs: the brief travels as query parameters, and the access gate is a
> cookie.

→ [ADR 005](adr/005-stream-runs-over-sse.md)

---

## 7. An append-only ledger, holding scenes too

Two BigQuery tables, written on every change. Memory is a read cache; a miss
falls back to a query.

```python
self._client.insert_rows_json(table, [row])   # streaming insert, queryable at once
```

- **BigQuery streaming inserts:** <https://cloud.google.com/bigquery/docs/streaming-data-into-bigquery>
- **Python client:** <https://cloud.google.com/python/docs/reference/bigquery/latest>
- Source: [`app/services/ledger.py`](../app/services/ledger.py)

> **The bug this fixed.** `save_scene` was inherited from the in-memory class, so
> scenes lived only in the instance that drafted them. On Cloud Run a writer
> could draft on one instance and land their decision on another — *"No such
> scene"*, decision lost. Visible only under concurrent load, i.e. exactly
> during judging.

→ [ADR 006](adr/006-append-only-ledger-in-bigquery.md)

---

## 8. Deploying: Cloud Run, scale to zero

```bash
gcloud run deploy sceneroom --source . \
  --min-instances 0 --max-instances 3 --timeout 600 --cpu-boost \
  --service-account sceneroom-run@PROJECT.iam.gserviceaccount.com \
  --set-secrets PARALLEL_API_KEY=parallel-api-key:latest
```

- **Cloud Run deploy:** <https://cloud.google.com/run/docs/deploying-source-code>
- **Secret Manager + Cloud Run:** <https://cloud.google.com/run/docs/configuring/services/secrets>
- **Vertex AI on Cloud Run auth:** <https://cloud.google.com/run/docs/securing/service-identity>

`min-instances 0` means ~$0 idle — the service must survive nine weeks of
judging on a small credit. `max-instances 3` caps what a public URL can spend.
No key material exists in the container; Vertex authenticates through the
metadata server.

→ [ADR 003](adr/003-cloud-run-not-agent-engine.md)

> **The bug that looked like success.** The Dockerfile copied `app/` but not
> `frontend/`. Because the static mount is guarded by `FRONTEND.is_dir()`, the
> container started healthy, passed `/api/health`, and served 404 at `/`. Now
> covered by [`tests/unit/test_packaging.py`](../tests/unit/test_packaging.py).

---

## 9. Evaluating: measure the thing, not the vibe

15 claims with known answers, run through the real verification path. Two error
types scored **separately**, because they are not equally bad:

- **wrong** — said verified when the truth is contradicted. Ships an error.
- **missed** — said `unverifiable` when there was an answer. Costs a decision.

```
base   10/15 correct · 5 missed · 0 wrong
pro    13/15 correct · 1 missed · 1 WRONG   <- ruled on a live dispute
pro,   12/15 correct · 3 missed · 0 wrong   <- after an instruction fix
after
```

The eval contradicted us on the first run: the "better" setting scored higher
*and* ruled on a genuinely disputed question — the one thing the product must
never do. The fix was an instruction, not a model.

Run: `uv run python evals/run_eval.py --compare` ·
Source: [`evals/`](../evals/)

> **Why not `agents-cli eval`?** It drives an agent over ADK's session protocol
> (`/apps/<app>/users/<u>/sessions`). Sceneroom serves its own API and has no
> single `root_agent`, so `eval generate` 404s. Tested, not assumed. If you
> **are** building a conventional ADK agent, use it — it gives you LLM-judge
> metrics and `eval compare` for free.
> <https://google.github.io/adk-docs/evaluate/>

---

## 10. One generated frame

```python
await client.aio.models.generate_content(
    model="gemini-3.1-flash-image",
    contents=prompt,
    config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
)
```

- **Image generation:** <https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images>
- **google-genai SDK:** <https://googleapis.github.io/python-genai/>
- Source: [`app/services/frame.py`](../app/services/frame.py)

> `generate_images` is deprecated in favour of `generate_content`, and the
> `imagen-*` publisher models were **not available** to our project in any
> region. Listing what the project can actually see was the only reliable way to
> find that out:
> ```python
> for m in genai.Client(vertexai=True, location="global").models.list(): print(m.name)
> ```

---

## 11. Five times the docs were wrong

The single most useful habit on this project: **check the installed package or
the live API, never the summary.**

| Claim | Reality |
|---|---|
| ADK graph edges are a 3-tuple | They are tuple chains with a `{route: target}` dict |
| `google.adk.skills.load_skills_from_dir` exists | It does not — only the singular `load_skill_from_dir` |
| `pip install mcp` works with ADK | 2.x moved a module ADK imports; the toolset vanishes silently |
| `imagen-*` is the image model | Not available to this project; `generate_images` deprecated |
| A `Workflow` node cannot see context | It can — state persists across nodes; input arrives as `node_input` |

The last one was *our* error, from reading ADK's source instead of its docs —
because the cached docs we had were five months stale and predated the graph API
entirely.

**ADK docs index:** <https://adk.dev/llms.txt> ·
**Full text:** <https://adk.dev/llms-full.txt>

---

## 12. Run it yourself

```bash
uv sync
uv run --with pytest pytest tests -q          # 47 tests
uv run --with ruff ruff check app tests evals tools

env -u GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT=<project> \
  uv run uvicorn app.fast_api_app:app --port 8080
```

`/api/health` reports whether Parallel is live, which ledger is active, and who
escalations route to. Check it first when something looks wrong.

Without a `PARALLEL_API_KEY` everything still runs on offline fixtures, and the
UI says so in the top bar — a demo must never pass fixture data off as live
search.

### Reference index

| Topic | Link |
|---|---|
| ADK docs | <https://adk.dev/> |
| ADK graph workflows | <https://adk.dev/graphs/> |
| ADK MCP tools | <https://adk.dev/tools/mcp-tools/> |
| ADK evaluation | <https://google.github.io/adk-docs/evaluate/> |
| Parallel Search API | <https://docs.parallel.ai/> |
| Parallel Search MCP | <https://docs.parallel.ai/integrations/mcp/search-mcp> |
| Model Context Protocol | <https://modelcontextprotocol.io/> |
| Vertex AI generative AI | <https://cloud.google.com/vertex-ai/generative-ai/docs> |
| Cloud Run | <https://cloud.google.com/run/docs> |
| BigQuery streaming | <https://cloud.google.com/bigquery/docs/streaming-data-into-bigquery> |
| Secret Manager | <https://cloud.google.com/secret-manager/docs> |
