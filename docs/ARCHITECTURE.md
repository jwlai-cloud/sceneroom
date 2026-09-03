# Architecture

_What is actually built, as of 2026-08-07. Interactive topology:
[`sceneroom-agents.html`](sceneroom-agents.html)._

Live: <https://sceneroom-320877670799.us-central1.run.app>

## The shape in one paragraph

A writer gives a brief. Seven Gemini agents draft a scene, pull every checkable
claim out of it, check those claims against the production bible and the open
web, and classify each one. Nothing is decided by an agent: claims that need a
person are routed to one by a pure function, the writer chooses fix / keep as
deliberate / escalate, and the choice plus its rationale and sources is appended
to a BigQuery ledger. A `fix` sends the scene back through extraction and
checking, so a correction cannot silently introduce a new error.

## The structural decision

**No agent has a tool, calls another agent, or reaches the web.** Retrieval is
Python in the orchestrator; the sources are pasted into the next agent's prompt.

That buys three things:

1. **Citations cannot be hallucinated.** Every URL in the UI came out of a
   Parallel response. A model that searches can invent a plausible source; one
   that is handed sources cannot.
2. **The sequence is deterministic.** Control flow, not a model deciding what to
   do next — which is what the brief asks a multi-step agent to demonstrate.
3. **"No sources" stays honest.** `_check_factual` short-circuits to
   `unverifiable` before any model call, so absence of evidence never reaches a
   model that might rationalise it into support.

The **one exception** is the Fandom agent, which holds Parallel's MCP tools.
Its question — *what has this audience already litigated?* — is iterative: spot
a controversy, read what the objection actually was, trace what it cost. It is
trusted to choose evidence about *what has been argued about*, never about
*what is true*.

## The crew

| Agent | Asks | Grounded in |
|---|---|---|
| **Writer** | Turn a brief into a scene | — |
| **Extractor** | What in this scene is checkable? | the scene text |
| **Continuity** | Does this contradict our own canon? | the production bible, **no search** |
| **Verifier** | Is this true? | Parallel **Search API**, orchestrator-retrieved |
| **Fandom** | What has this audience objected to before? | Parallel **MCP** (`web_search`, `web_fetch`) |
| **Rights** | Does using this need permission? | Parallel Search API |
| **Adjudicator** | What must a human see? | `route()` — **a pure function**, plus a model that writes the handoff note |

Every agent is one ADK `LlmAgent` on `gemini-flash-latest`: single turn,
`output_schema`, no retries loop. Many small structured calls, not deep
reasoning.

### Fixing is a graph, not a call

Choosing **fix it** runs an ADK `Workflow`:

    START -> prepare -> reviser -> stash -> critic -> route
                 ^                                     |
                 +--------------- "retry" -------------+   ("done" -> finish)

`prepare`, `stash`, `route` and `finish` are ordinary Python; only `reviser` and
`critic` are models. The critic reads the rewrite and decides whether the
correction actually landed — before that, any non-empty rewrite was accepted and
a revision that changed the wording but not the fact went straight into another
full round of live checking.

Routing is `decide_route`, a pure function. That is the same argument as the
Adjudicator below, and it is why this is a graph rather than a `LoopAgent`:
`LoopAgent` terminates on `escalate`, set from inside a tool on the model's own
agent, so the decision to stop lived with the model. See
[ADR 007](adr/007-workflow-graph-over-loopagent.md).

### The Adjudicator is split on purpose

Routing is `route()` in `app/agents/adjudicator.py` — pure, total, unit-tested.
The product's one hard guarantee is that contested history always reaches a
human; a guarantee implemented as a prompt is not a guarantee. The model only
writes the note for the person picking it up, and is instructed never to say
which side of a dispute is right.

## Four verdicts, three dispositions

Verdicts are what checking established: `verified`, `contradicted`,
`contested`, `unverifiable`. Dispositions are what the human chose: **fix**,
**keep — deliberate**, **escalate**. Agents never set a disposition.

`contested` is the load-bearing one. It means credible sources actively
disagree, and it is *not* a weaker `contradicted` — the UI gives it its own
colour in every theme for exactly this reason.

`keep — deliberate` is the product's thesis: artistic licence recorded as a
choice, with the real fact filed beside it. The rationale is required.

**Mode changes one threshold, not the engine.** In `documentary`, an
`unverifiable` claim reaches a human; in `fiction` it is recorded as unsupported
and the writer carries on.

## Runtime

```
Browser ──SSE──> Cloud Run (FastAPI, min-instances 0, max-instances 3)
                    ├─ Vertex AI · gemini-flash-latest      (7 agents)
                    ├─ Vertex AI · gemini-3.1-flash-image   (one payoff frame)
                    ├─ Parallel Search API                  (Verifier, Rights)
                    ├─ Parallel MCP                         (Fandom)
                    ├─ BigQuery  agent-era.sceneroom.*       (ledger)
                    └─ Secret Manager                        (keys)
```

A pass takes ~30s and is **streamed**, not awaited: each agent reports when it
starts, how long it took and what it found. Polling was rejected because it
needs shared state and Cloud Run spreads polls across instances.

**Security.** Runtime service account `sceneroom-run@agent-era` holds
`aiplatform.user`, `secretmanager.secretAccessor`, `bigquery.jobUser`, and
`WRITER` on the `sceneroom` dataset only — no project-wide `dataEditor`. No key
material exists in the container; Vertex authenticates through the metadata
server. The public URL is behind a cookie-based access code, because every run
behind it spends money.

## Files worth knowing

| Path | What lives there |
|---|---|
| `app/orchestrator.py` | the workflow, and the only caller of Parallel |
| `app/agents/` | seven agents, one file per question |
| `app/agents/adjudicator.py` | `route()` — the escalation rule, as code |
| `app/agents/revise_workflow.py` | the fix/critique graph, and its routing function |
| `app/services/parallel_client.py` | Search API seam + offline fixtures |
| `app/services/parallel_mcp.py` | the MCP toolset, given to one agent |
| `app/services/ledger.py` | append-only provenance, in-memory or BigQuery |
| `app/services/runs.py` | run events, the crew timeline's data |
| `app/services/frame.py` | the single payoff frame |
| `frontend/` | the console: script page, inline flags, ledger |

## What this does not claim

It does not guarantee correctness. Retrieval is not omniscience, sources
conflict, and some disputes are contested historiography between states rather
than facts to look up. The claim is **"no unreviewed claim ships"** — which is
demonstrable, and which is why the ledger exists.
