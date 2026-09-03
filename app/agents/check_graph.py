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

"""The check phase as an ADK graph, with a runtime-sized fan-out.

The number of claims is not known until the Extractor has run, so the shape of
this stage cannot be declared in advance. That is precisely what ADK's dynamic
nodes are for: a `@node` function gets the execution context and can call
`ctx.run_node()` as many times as the input turns out to require.

    START -> continuity -> check_all -> adjudicate
                             |
                             +-- ctx.run_node() per claim, concurrently

`check_all` is ordinary Python that happens to be a graph node. Every claim
becomes a child run, so the graph records the real shape of the work rather than
one opaque step.

Measured before writing this (tools were not trusted on the docstring alone):
five children under `asyncio.gather(ctx.run_node(...))` completed in 1.0s versus
5.01s awaited one at a time, and a failing child surfaced as
`DynamicNodeFailError` rather than being swallowed. The API's warning about
unsupervised tasks is about `create_task`, not `gather`.

The run tracker is threaded through closures rather than graph state: the SSE
timeline is the product's most convincing surface and must keep reporting each
agent as it starts, whatever the orchestration underneath.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from google.adk import Workflow
from google.adk.workflow import START, node

from app.models import Claim, ClaimKind, Scene, Verdict

logger = logging.getLogger(__name__)

# A scene has a handful of claims; cap concurrency so a long scene cannot fan
# out into a rate-limit wall.
MAX_CONCURRENT_CHECKS = 6

GROUPS = ("verifier", "fandom", "rights")


def group_of(claim: Claim) -> str | None:
    """Which checking agent owns this claim. Canon is handled by Continuity."""
    if claim.kind == ClaimKind.CANON:
        return None
    if claim.kind == ClaimKind.FANDOM:
        return "fandom"
    if claim.kind == ClaimKind.RIGHTS:
        return "rights"
    return "verifier"


def build_check_workflow(
    scene: Scene,
    checkers: dict[str, Callable[[Claim, Scene], Awaitable[None]]],
    continuity: Callable[[], Awaitable[None]],
    adjudicate: Callable[[], Awaitable[None]],
    step: Callable[[str], Any],
    note: Callable[[str, str], None],
) -> Workflow:
    """The check phase as a graph, over the claims this scene actually has.

    Built per scene, because the fan-out width is a property of the scene. The
    callables are passed in rather than imported so this module never reaches
    back into the orchestrator — the graph describes the shape, the orchestrator
    still owns the behaviour.
    """
    sem = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

    async def run_continuity(node_input: Any) -> Scene:
        await continuity()
        return scene

    @node(rerun_on_resume=True)
    async def check_all(node_input: Any, ctx: Any) -> Scene:
        """Runtime-sized fan-out: one child run per claim, grouped by agent."""
        grouped: dict[str, list[Claim]] = {g: [] for g in GROUPS}
        for claim in scene.claims:
            g = group_of(claim)
            if g:
                grouped[g].append(claim)

        async def run_group(name: str) -> None:
            claims = grouped[name]
            async with step(name) as s:
                if not claims:
                    if s is not None:
                        from app.services.runs import StepStatus

                        s.status = StepStatus.SKIPPED
                        s.detail = "nothing of this kind in the scene"
                    return
                done = 0

                async def one(claim: Claim) -> None:
                    nonlocal done
                    async with sem:
                        # A child run of this node, so the graph sees per-claim
                        # work. Awaited inside gather — measured concurrent.
                        await ctx.run_node(
                            _checker_node(name, claim, checkers[name], scene),
                            node_input=claim.id,
                            # Concurrent children: isolate their events from the
                            # parent branch rather than interleaving them.
                            use_sub_branch=True,
                        )
                    done += 1
                    note(name, f"checked {done} of {len(claims)}")

                await asyncio.gather(*(one(c) for c in claims))
                flagged = sum(1 for c in claims if c.needs_attention)
                if s is not None:
                    s.detail = (
                        f"{len(claims)} checked, {flagged} flagged"
                        if flagged
                        else f"{len(claims)} checked, all clear"
                    )

        await asyncio.gather(*(run_group(g) for g in GROUPS))
        return scene

    async def run_adjudicator(node_input: Any) -> Scene:
        await adjudicate()
        return scene

    return Workflow(
        name="check_scene",
        description="Continuity, then a per-claim fan-out, then adjudication.",
        edges=[(START, run_continuity, check_all, run_adjudicator)],
    )


def _checker_node(
    name: str,
    claim: Claim,
    checker: Callable[[Claim, Scene], Awaitable[None]],
    scene: Scene,
):
    """One claim's check, as a callable ADK can run as a child node.

    Named per claim so the graph's child runs are identifiable rather than a row
    of anonymous callables.
    """

    async def check(node_input: Any) -> str:
        try:
            await checker(claim, scene)
        except Exception:
            # One claim's check failing must not take the scene down, and must
            # never leave a verdict of None — `route()` reads that as "sources
            # support this", which would ship an unchecked claim as clean.
            logger.exception("check failed for claim %s (%s)", claim.id, name)
            claim.verdict = Verdict.UNVERIFIABLE
            claim.reasoning = "This check did not complete. Nothing was established either way."
        return claim.verdict.value if claim.verdict else "unchecked"

    check.__name__ = f"{name}_{claim.id.replace('-', '_')}"
    return check
