# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Parallel's MCP server, given to exactly one agent.

Two ways into Parallel, used for two different jobs:

- **Search API** (`parallel_client`) for the Verifier. The orchestrator
  retrieves and hands the sources over, so the model cannot choose its own
  evidence and therefore cannot invent a citation. That is the guarantee the
  product rests on and it is not negotiable.
- **MCP** (here) for the Fandom agent, which asks a different kind of question:
  *what has this audience already litigated about this period?* Answering it is
  iterative — search, notice a controversy, read that article, search again for
  what it cost the production. One fixed query cannot do that, so this agent is
  given `web_search` and `web_fetch` and left to work.

Giving MCP to the Verifier as well would be easy and wrong: it would hand the
adjudication of truth to whatever the model chose to look at.

Verified against the installed packages, not a cheatsheet:
- `MCPToolset` is keyword-only and takes `connection_params` + `tool_filter`.
- ADK 2.5 supports `output_schema` together with `tools` — tools run during the
  thought loop, structure is enforced on the final answer.
- `mcp` must be <2.0: 2.x moved `mcp.shared.session`, which ADK 2.5 imports.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Streamable HTTP, per Parallel's docs. The /mcp endpoint also serves anonymous
# callers at a lower rate limit; we send the key, so we get the real one.
PARALLEL_MCP_URL = os.getenv("PARALLEL_MCP_URL", "https://search.parallel.ai/mcp")

_toolset = None
_tried = False


def build_search_toolset():
    """The Parallel MCP toolset, or None if it cannot be built.

    Cached: a toolset holds MCP sessions, and constructing one per claim would
    open a connection per claim. None is a normal answer — without a key, or
    without the optional `mcp` package, the Fandom agent falls back to the
    orchestrator-retrieved path and the product still works.
    """
    global _toolset, _tried
    if _toolset is not None:
        return _toolset

    from app.services.parallel_client import PARALLEL_API_KEY

    if not PARALLEL_API_KEY:
        # No key is a settled answer, not a transient one.
        _tried = True
        logger.info("No Parallel key; Fandom will use the retrieved-sources path.")
        return None

    # A failure is NOT cached. Latching it meant one bad construction on a cold
    # instance made that instance report MCP unavailable for its whole life,
    # including to /api/health, while other instances served it fine.
    if _tried and _toolset is None:
        logger.debug("Retrying the Parallel MCP toolset after an earlier failure")

    try:
        from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams

        _toolset = MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=PARALLEL_MCP_URL,
                headers={"Authorization": f"Bearer {PARALLEL_API_KEY}"},
            ),
            # Only what this agent should be able to do. The server may grow
            # more tools; this one searches and reads, nothing else.
            tool_filter=["web_search", "web_fetch"],
        )
        logger.info("Parallel MCP toolset ready: %s", PARALLEL_MCP_URL)
    except Exception as exc:
        # Never take the product down for an optional retrieval path.
        logger.warning("Parallel MCP unavailable (%s); using the Search API path", exc)
        _toolset = None
    return _toolset


def is_live() -> bool:
    return build_search_toolset() is not None
