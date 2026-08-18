# 007 — The Workflow graph, not LoopAgent

**Status:** Accepted · 2026-08-08 (superseded the earlier decision to keep LoopAgent)

## Context

The revise/critique cycle is built as an ADK `LoopAgent`. ADK 2.5 emits:

> `LoopAgent is deprecated in favor of Workflow and will be removed in a future
> version. Workflow cannot yet be used as an LlmAgent sub-agent.`

So the primitive we used is on the way out, and the question "are you using ADK
properly?" has a sharper edge than it looks.

## What was actually checked

Not assumed — probed against the installed package:

- `google.adk.workflow` exists and exports `Workflow`, `Node`, `FunctionNode`,
  `JoinNode`, `START`, `DEFAULT_ROUTE`, `Edge`.
- Edges are tuple chains, and a `dict` inside a chain is a routing map —
  `(critic, {"not_fixed": reviser})`. This matches the note in `CLAUDE.md` that
  the 2.5 edge API is a `{route: target}` dict rather than a 3-tuple.
- **A cycle is accepted.** `Workflow(edges=[(START, reviser), (reviser, critic),
  (critic, {"not_fixed": reviser})])` builds, three edges, no complaint. The
  loop shape is not the obstacle.
- A node routes by setting `tool_context.actions.route`, and the key must match
  the edge exactly. The first probe emitted `"Not Fixed"` against a
  `"not_fixed"` edge and ADK logged *"none were matched by the emitted route(s)
  ... The branch will end."*

## What the probe got wrong

The first reading of this was that a `Workflow` node "cannot see context",
because `run_llm_agent_as_node` sets an `LlmAgent` node to `mode='single_turn'`
with `include_contents='none'`, and the probe's reviser returned a placeholder
saying its context was missing.

Reading the current documentation (adk.dev, not the stale cached copy) corrects
that:

- **State does persist across nodes.** The docs list three channels — `output`
  passes data node to node, `message` is the user-facing response, and `state`
  is "data automatically persisted across nodes via Events throughout an ADK
  session". Nothing is lost; the reviser simply was not given its input the way
  a node receives one.
- **Routing is not done from inside an LlmAgent.** The idiomatic shape is an
  LlmAgent that classifies, followed by a plain function node that returns
  `Event(route=[...])`, with the dict edge dispatching on that. The probe tried
  to route from a tool on the agent itself and fed the model's free-text verdict
  in as the key, which is why `"Not Fixed"` never matched `"not_fixed"`.

So the port is smaller than it first looked, and it fits this codebase better
than `LoopAgent` does: the routing decision becomes a deterministic function
node, which is exactly the argument in ADR 002. The docs describe the point of
the graph API in those terms — "switching between non-deterministic AI-powered
agents and deterministic code as needed".

The shape would be:

    Workflow(edges=[
        (START, reviser, critic),
        (critic, route_fn),                       # returns Event(route=[...])
        (route_fn, {"not_fixed": reviser}),       # no edge for "fixed" -> ends
    ])

with the claim and sources in state, and the scene passed node to node.

## Decision

Ported. The revise cycle is now a `Workflow`:

    START -> prepare -> reviser -> stash -> critic -> route
                 ^                                     |
                 +--------------- "retry" -------------+   ("done" -> finish)

`prepare`, `stash`, `route` and `finish` are ordinary Python; only `reviser` and
`critic` are models.

The deciding argument was not the deprecation warning. It is that **the routing
decision becomes a plain function**, which is ADR 002 restated — the model
judges, code decides what happens next. The docs describe the graph API in those
exact terms: "switching between non-deterministic AI-powered agents and
deterministic code as needed".

`LoopAgent` could not express that. Its termination signal is `escalate`, set
from inside a tool on the model's own agent, so the decision to stop lived with
the model. Here it lives in `decide_route`.

## Consequences

- No deprecation warning, and no `LoopAgent`.
- **Route keys are normalised in code, not asked for in a prompt.** The first
  attempt failed because the model answered "Not Fixed" against a `"not_fixed"`
  edge; a route is matched exactly, so no edge matched, the branch ended
  silently, and the retry was simply lost. `normalise_verdict` now maps anything
  that is not an acceptance to `not_fixed` — ambiguity falls towards checking
  again, never towards shipping.
- The claim and finding travel in a closure rather than session state. The
  workflow is built per decision, so they are constants for its whole life and
  cannot drift the way a shared key can.
- The deterministic parts are module-level pure functions the graph wraps rather
  than closures buried in nodes. The first test pass could not reach them
  without guessing at ADK's node internals, which was the design telling on
  itself.
- An explicit `finish` node terminates the accepted route. A route with no edge
  also ends the branch, but ADK logs a warning every time — noise on the
  successful path.

Verified live: the Motorola handie-talkie became a period-correct police call
box, verdict `fixed` on the first attempt. 47 unit tests.

## Corroboration

Google Cloud published *"ADK 2: Collaborative Multi-Agent Patterns"* on
2026-08-15, after this port was made. It agrees on both counts:

- It names `LoopAgent` a **deprecated loop construct** and offers Drafter +
  Critic peer review as the replacement — structurally what this graph does.
- Its decision matrix opens with *"Can I draw the complete flowchart on a
  whiteboard before the user inputs anything?"* → if yes, use `Workflow` for
  deterministic execution. Ours is drawable, and drawn:
  [`sceneroom-agents.html`](../sceneroom-agents.html).

One deliberate divergence. The article's Pattern 3 uses an **Agent** as the
supervisor coordinating drafter and critic. Ours routes with a **function node**
(`decide_route`). For a product whose claim is auditability, the decision to
stop belongs in code — ADR 002 restated.

The pattern the article names that we do **not** use is the
Coordinator-Dispatcher, and deliberately: it applies when *the user's message*
dictates which expert responds. Here the claim's *kind* does, decided by the
Extractor and dispatched by a static map. A model-driven dispatcher would add
nondeterminism exactly where it was removed on purpose.

<https://medium.com/google-cloud/google-adk-2-collaborative-multi-agent-patterns-a-practical-guide-5c696ba556d2>

## What would change this

Nothing about the shape. If the cycle ever needs to fan out — several revisions
judged in parallel and joined — that is `JoinNode`, already in the same API.
