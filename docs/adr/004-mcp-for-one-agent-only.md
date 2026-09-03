# 004 — Parallel MCP for the Fandom agent only

**Status:** Accepted · 2026-08-07

## Context

The PRD calls for Parallel's MCP server *and* its Search API. The simplest way
to satisfy that is to move all retrieval to MCP and give every agent the tools —
but that would reverse ADR 001 and hand the adjudication of truth to whatever
the model chose to look at.

Meanwhile the Fandom agent had a real problem. Its question is *what has this
audience already litigated about this period?* Answering it is iterative: notice
a controversy, read what the objection actually was, search again for what it
cost the production. A single fixed query answers a different, shallower
question.

## Decision

Two paths into Parallel, for two different jobs:

- **Search API** for the Verifier and Rights — orchestrator-retrieved, per ADR 001.
- **MCP** (`web_search`, `web_fetch`) for the Fandom agent, which searches for
  itself and reports the sources it actually opened.

The distinction is what each is trusted with. Fandom chooses evidence about
*what has been argued about*. It is never asked what is true.

## Consequences

- Markedly better results where it matters. On a Joseon 1443 scene the agent
  found the *Joseon Exorcist* cancellation and cited an academic journal
  alongside Korea Times and HanCinema — sources a single query did not surface.
- Degrades safely: without a key, without the `mcp` package, or with the server
  unreachable, Fandom falls back to orchestrator-retrieved sources.
- The schema is the same on both paths, so nothing downstream knows which ran.

## Trap recorded

`mcp` 2.x moved `mcp.shared.session`, which ADK 2.5 imports. Installing plain
`mcp` resolves to 2.x and the toolset **silently disappears** — ADK catches the
ImportError and logs it at debug level. The dependency is pinned `<2.0`.
