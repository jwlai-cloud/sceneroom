# Sceneroom — Devpost submission

**Live:** <https://sceneroom-320877670799.us-central1.run.app>
**Access code:** `jongno-1963-50f10b` _(each run spends on Gemini and Parallel, so the room is gated)_
**Track:** Parallel · **Repo:** <https://github.com/jwlai-cloud/sceneroom>

---

## Project name

    Sceneroom — no unreviewed claim ships

## Elevator pitch

_(195 chars, fits Devpost's 200)_

    A scene room that writes, then refuses to let the scene ship unchecked. It
    never adjudicates contested history — it escalates. You get a
    production-ready scene and the record of who decided what.

**Thumbnail:** [`sceneroom-thumbnail.jpg`](sceneroom-thumbnail.jpg) — 1200×800,
pulled from the demo at the payoff frame.

---

## Inspiration

In June 2026, MBC's *21st Century Grand Princess* drew sustained criticism for
verification errors and historical distortion. The production team and cast
issued public apologies, and the argument carried on online well after the
apology. Those are post-air costs for a pre-air failure.

The interesting part is who caught it: **viewers**. Fans are the industry's de
facto continuity QA — they maintain the wikis, track the props, and litigate the
lore. The production had no equivalent scrutiny before air.

Meanwhile AI-native studios are scaling into exactly this market. They ship
faster, they have no standards & practices department, and generated content
doesn't merely *miss* period errors — it **invents** them, already sounding
plausible.

But the obvious product would be wrong. A tool that flags every historical
deviation is creativity police. *Bridgerton* is deliberately anachronistic;
*Inglourious Basterds* rewrites the war on purpose. Artistic licence is not an
error.

The distinction that matters is **informed vs. accidental**.

## What it does

A writer gives a brief — *"night scene, Seoul 1963, the detective loses her
badge."* Then seven agents:

1. **Writer** drafts the scene.
2. **Extractor** pulls out every checkable claim.
3. **Continuity** checks the production bible — internal canon, no web.
4. **Verifier** checks each claim against the open web via **Parallel**.
5. **Fandom** asks a different question — *what has this audience already
   litigated?* — using **Parallel's MCP server** to search and read for itself.
6. **Rights** asks whether using something needs permission. It can never say
   "cleared"; the best verdict available is "no obstacle found".
7. **Adjudicator** decides what a human must see.

Flags appear **inline on the script page**, each linked to a margin note with
its sources. Every flag offers three answers, not two:

- **Fix it** — the scene is revised, then **re-extracted and re-checked**, so a
  correction can't silently introduce a new error.
- **Keep — deliberate** — artistic licence, recorded as a choice with the real
  fact filed beside it. A rationale is required.
- **Escalate** — routed to a human.

Everything lands in an **append-only BigQuery ledger**. You can download the
provenance record as a document.

One **generated frame** of the signed-off scene closes the loop.

### The part we're proudest of

**`contested` is a verdict, and the system refuses to resolve it.**

When credible sources actively disagree — the Northeast Project, portrayals of
real historical figures — the agent does not pick a side. It says so, states the
competing positions even-handedly, and routes to a named human.

An agent that knows the limits of its own authority is worth more than one
claiming omniscience. A production needs "get a consultant" as much as it needs
"this date is wrong".

## How we built it

**Google Cloud:** Gemini via Vertex AI (7 ADK agents), Gemini image generation
(the payoff frame), BigQuery (the ledger), Cloud Run (hosted), Secret Manager,
least-privilege service account.
**Partner:** Parallel Search API **and** Parallel MCP server.

### Seven agents, and one graph

Six of the seven are single-turn `LlmAgent`s with an `output_schema`. The
seventh path — choosing **fix it** — is an ADK **`Workflow` graph**:

    START -> prepare -> reviser -> stash -> critic -> route
                 ^                                     |
                 +--------------- "retry" -------------+

Only `reviser` and `critic` are models; `prepare`, `stash` and `route` are
ordinary Python. Before this, any non-empty rewrite was accepted, so a revision
that changed the wording but not the fact went into another full round of live
checking on the writer's time.

We built it as a `LoopAgent` first and ported it. Not because ADK deprecates
`LoopAgent`, but because the graph makes **the routing decision a plain
function** — the ADK docs describe the graph API as *"switching between
non-deterministic AI-powered agents and deterministic code as needed"*, which is
the same argument as the guarantee below. `LoopAgent` terminates on `escalate`,
set from inside a tool on the model's own agent, so the decision to stop lived
with the model.

### The structural decision: agents have no tools

Retrieval lives in Python. The orchestrator calls Parallel and pastes the
sources into the agent's prompt. The Verifier is told outright: *"You do not use
prior knowledge as evidence — only what the sources say."*

Three consequences:

1. **A citation cannot be hallucinated.** Every URL came out of a Parallel
   response, not a model.
2. **The pipeline is deterministic** — control flow, not a model choosing a next
   step.
3. **"No sources" stays honest** — it short-circuits to `unverifiable` before
   any model call, so absence of evidence never reaches a model that might
   rationalise it into support.

**One exception: the Fandom agent holds Parallel's MCP tools.** Its question is
iterative — spot a controversy, read what the objection was, trace what it cost.
It's trusted to choose evidence about *what has been argued about*, never about
*what is true*.

### The guarantee is code, not a prompt

Whether a claim escalates is a **pure function**, unit-tested. The product's
hard rule is that contested history always reaches a human; a guarantee
implemented as a prompt drifts with model versions and can be argued out of. The
model only writes the handoff note.

## Challenges we ran into

**A successful deploy with no product in it.** The Dockerfile copied `app/` but
not `frontend/`. Because the static mount is guarded by `FRONTEND.is_dir()`, the
container started healthy, passed `/api/health`, and served 404 at `/`. Caught by
reading the Dockerfile against the code, now guarded by a test.

**The MCP toolset that silently disappeared.** `mcp` 2.x moved
`mcp.shared.session`, which ADK 2.5 imports — ADK catches the ImportError and
logs it at *debug*. Everything looked fine and MCP simply wasn't there. Pinned
`<2.0`.

**A routing bug wearing a 404's costume.** `/api/scenes/stream` was shadowed by
`/api/scenes/{scene_id}` and returned "No such scene."

**Decisions that could vanish.** Scenes lived only in the instance that drafted
them, so on Cloud Run a writer could draft on one instance and land their
decision on another — "No such scene", decision lost. Only visible under
concurrent load, i.e. exactly during judging.

**An agent that could never run.** Continuity skipped every pass because the
Extractor's instruction listed four claim kinds and `canon` wasn't one of them.

**Imagen wasn't available.** The `imagen-*` publisher models 404 for this
project in every region tried, and `generate_images` is deprecated. Listing the
models the project could actually see was the only reliable way to find out.

Every one of these was found by **running the thing** — several only by driving
the real page in a browser.

### We built an evaluation set, and it disagreed with us

Fifteen claims with known answers, two of them genuinely disputed. The two error
types are scored separately, because they are not equally bad — a *miss* costs
the writer a decision, a *wrong call* ships an error.

    base   9/15 correct · 6 missed · 0 wrong    <- shipped
    pro   11/15 correct · 3 missed · 1 WRONG    <- ruled on a live dispute

We had been telling ourselves the better search setting was simply better. It
scored higher **and** ruled on whether Sejong invented Hangul unaided — which
specialists genuinely dispute, and which is the one thing this product must
never do.

We fixed that once with an instruction, and it held. Then we re-ran the eval the
day before submitting, and the wrong call was back: the open web had moved under
us, and the same setting was again ruling on a live dispute. The eval is the only
reason we knew. Production now runs the setting that makes **zero wrong calls**,
and pays for it with six claims that come back unverifiable.

That is the trade this product exists to make. A miss costs the writer a
decision. A wrong call ships an error under our name.

## Accomplishments

- Seven agents, live, streaming their real timings and findings during the ~30s
  pass — the wait became the evidence rather than a spinner.
- Both Parallel surfaces used, for different jobs, with a defensible reason for
  the split.
- A durable, append-only audit trail that survives restarts and instance churn.
- `contested` handled as a first-class outcome instead of a hedge.
- Found the *Joseon Exorcist* cancellation unprompted, citing an academic
  journal alongside trade press — a real drama pulled after two episodes for
  exactly the failure this product exists to prevent.

## What we learned

- **Where you put the retrieval decides what you can promise.** Moving it out of
  the model turned "probably cited" into "cannot be otherwise".
- **A guarantee in a prompt isn't a guarantee.**
- **Waiting is a design problem, not a spinner problem.** 32 seconds of one
  unchanging sentence reads as a hang; the same 32 seconds of real agent
  progress is the most convincing thing on screen.
- **Cheatsheets were wrong four times.** Every one was caught by checking
  against the installed package or by running it.

## What's next

- **Multi-scene continuity.** The Continuity agent already checks a bible;
  checking scene 12 against scenes 1–11 is the obvious next step.
- **House-style skills.** Verification playbooks as loadable ADK Skills, so a
  standards desk adds its own guidelines without forking.
- **Named consultants** with real routing, so escalation reaches a person rather
  than a role.

## What it does not claim

It does not guarantee correctness. Retrieval isn't omniscience, sources
conflict, and some disputes are contested historiography between states rather
than facts to look up. The claim is **"no unreviewed claim ships"** — which is
demonstrable, and which is why the ledger exists.
