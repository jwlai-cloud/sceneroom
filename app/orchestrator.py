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

"""The Sceneroom workflow.

    intent -> draft -> extract -> check (canon | fact | fandom) -> decide
           -> revise -> re-check -> provenance

Claims are checked concurrently — they're independent, and a scene has 3-8 of
them, so doing it serially would triple the demo's latency for no reason.

The human decision in the middle is not a formality: agents never set a
`Disposition`, and `keep_deliberate` is how artistic licence gets recorded
rather than corrected.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from app.agents.adjudicator import build_adjudicator, route
from app.agents.check_graph import build_check_workflow
from app.agents.continuity import build_continuity
from app.agents.extractor import build_extractor
from app.agents.revise_workflow import build_revise_workflow
from app.agents.rights import build_rights
from app.agents.verifier import build_fandom, build_verifier
from app.agents.writer import build_writer
from app.models import (
    Claim,
    ClaimKind,
    Disposition,
    Mode,
    RevisionEntry,
    Scene,
    Source,
    Verdict,
)
from app.services import parallel_client, parallel_mcp
from app.services.ledger import get_ledger
from app.services.runner import run_agent, run_agent_state
from app.services.runs import RunTracker, StepStatus

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def _step(tracker: RunTracker | None, agent: str):
    """Time an agent's turn when a tracker is watching; no-op when none is.

    Lets every entry point stay usable without streaming — the plain JSON API
    and the tests pass None and behave exactly as they did before.
    """
    if tracker is None:
        yield None
        return
    async with tracker.step(agent) as step:
        yield step


def _detail(step, text: str) -> None:
    if step is not None:
        step.detail = text


def _skip(step, text: str) -> None:
    """An agent with nothing to do says so, rather than silently vanishing."""
    if step is not None:
        step.status = StepStatus.SKIPPED
        step.detail = text

# A scene has a handful of claims; cap concurrency so a long scene can't fan out
# into a rate-limit wall.
_MAX_CONCURRENT_CHECKS = 6


async def draft_scene(
    intent: str,
    project: str,
    mode: Mode,
    setting: str = "",
    bible: str = "",
    tracker: RunTracker | None = None,
) -> Scene:
    """Step 1: turn the writer's brief into a scene."""
    prompt = f"Brief: {intent}"
    if setting:
        prompt += f"\nSetting: {setting}"

    async with _step(tracker, "writer") as step:
        out = await run_agent(build_writer(), prompt)
        _detail(step, f"drafted {len(out.get('text', ''))} characters")

    scene = Scene(
        id=f"sc-{uuid.uuid4().hex[:8]}",
        project=project,
        mode=mode,
        intent=intent,
        setting=out.get("setting") or setting,
        text=out.get("text", ""),
        bible=bible,
    )
    get_ledger().save_scene(scene)
    get_ledger().append_revision(
        RevisionEntry(
            revision=1,
            scene_id=scene.id,
            what_changed="Scene drafted from brief",
            why=intent,
        )
    )
    return scene


async def load_demo_scene(project: str = "demo", mode: Mode = Mode.FICTION) -> Scene:
    """A pinned scene whose details match the offline fixtures, so the loop can
    be walked through without credentials. Always labelled as sample data."""
    from app import demo

    scene = Scene(
        id=f"sc-{uuid.uuid4().hex[:8]}",
        project=project,
        mode=mode,
        intent="Sample scene — a detective loses her badge in a Jongno alley.",
        setting=demo.DEMO_SETTING,
        text=demo.DEMO_TEXT.strip(),
        claims=[
            Claim(
                id=f"cl-{uuid.uuid4().hex[:8]}",
                kind=ClaimKind(c["kind"]),
                text=c["text"],
                excerpt=c["excerpt"],
            )
            for c in demo.DEMO_CLAIMS
        ],
    )
    get_ledger().save_scene(scene)
    get_ledger().append_revision(
        RevisionEntry(
            revision=1,
            scene_id=scene.id,
            what_changed="Sample scene loaded",
            why="Demonstration without live search credentials",
        )
    )
    return await check_claims(scene)


async def extract_claims(scene: Scene, tracker: RunTracker | None = None) -> list[Claim]:
    """Step 2: pull out everything checkable."""
    # The bible goes to the Extractor as well as to Continuity: an extractor
    # that has never seen the bible cannot know which details are canon, so
    # Continuity would be handed nothing to check and skip every time.
    prompt = (
        f"Setting: {scene.setting}\n"
        f"Production type: {scene.mode.value}\n\n"
        + (f"Production bible:\n{scene.bible}\n\n" if scene.bible.strip() else "")
        + f"Scene:\n{scene.text}"
    )
    async with _step(tracker, "extractor") as step:
        out = await run_agent(build_extractor(), prompt)
        _detail(step, f"{len(out.get('claims', []))} checkable claims")

    claims: list[Claim] = []
    for raw in out.get("claims", []):
        kind_str = str(raw.get("kind", "factual")).lower().strip()
        try:
            kind = ClaimKind(kind_str)
        except ValueError:
            kind = ClaimKind.FACTUAL
        claims.append(
            Claim(
                id=f"cl-{uuid.uuid4().hex[:8]}",
                kind=kind,
                text=str(raw.get("text", "")).strip(),
                excerpt=str(raw.get("excerpt", "")).strip(),
            )
        )
    return [c for c in claims if c.text]


async def _check_factual(claim: Claim, scene: Scene) -> None:
    # Parallel ranks by intent, so the objective says what would settle the
    # question, not just what the claim is. Naming the kinds of source that
    # count keeps period claims off marketplace and video listings, which is
    # what a bare restatement of the claim was returning.
    objective = (
        f"Determine whether this is historically accurate for "
        f"{scene.setting or 'the stated period'}: {claim.text}. "
        f"Prefer archives, museum and government records, encyclopaedic "
        f"references, contemporaneous reporting and academic sources. "
        f"State what was actually the case at that date."
    )
    sources = await parallel_client.search(objective)
    claim.sources = sources

    if not sources:
        claim.verdict = Verdict.UNVERIFIABLE
        claim.reasoning = "No sources found. Absence of evidence is not support."
        return

    prompt = (
        f"Claim: {claim.text}\n"
        f"Setting: {scene.setting}\n\n"
        f"Sources:\n{_format_sources(sources)}"
    )
    out = await run_agent(build_verifier(), prompt)
    claim.verdict = _parse_verdict(out.get("verdict"))
    claim.reasoning = str(out.get("reasoning", ""))


async def _check_fandom_via_mcp(claim: Claim, scene: Scene, toolset) -> None:
    """The agentic path: the Fandom agent searches and reads for itself.

    Precedent is found iteratively — spot a controversy, read what it actually
    was, trace what it cost the production — so a single fixed query answers the
    wrong question. This is the one place a model is trusted to choose its own
    evidence, and it is trusted with "what has been argued about", never with
    "what is true".
    """
    prompt = (
        f"Subject: {claim.text}\n"
        f"Setting: {scene.setting}\n"
        f"Production type: {scene.mode.value}\n\n"
        f"Research what audiences and critics have objected to in comparable "
        f"productions, and report documented precedent with the sources you read."
    )
    out = await run_agent(build_fandom(tools=[toolset]), prompt)

    claim.precedent = str(out.get("precedent", ""))
    claim.reasoning = str(out.get("reasoning", ""))
    claim.sources = [
        Source(title=str(s.get("title", "")), url=str(s.get("url", "")))
        for s in (out.get("sources") or [])
        if s.get("url")
    ]

    if not claim.sources:
        # It searched and came back empty-handed. That is an answer, but it is
        # not evidence of a flashpoint.
        claim.verdict = Verdict.UNVERIFIABLE
        claim.reasoning = claim.reasoning or "No documented precedent found."
        return

    claim.verdict = Verdict.CONTESTED if out.get("is_flashpoint") else Verdict.VERIFIED


async def _check_fandom(claim: Claim, scene: Scene) -> None:
    # Precedent, not prediction: ask what comparable productions were criticised
    # for, which is a real, indexed question.
    objective = (
        f"Find documented audience or critical objections to how productions "
        f"set in {scene.setting or 'this period'} have handled: {claim.text}. "
        f"Include past controversies and their consequences."
    )
    sources = await parallel_client.search(objective)
    claim.sources = sources

    if not sources:
        claim.verdict = Verdict.UNVERIFIABLE
        claim.reasoning = "No documented precedent found."
        return

    prompt = (
        f"Subject: {claim.text}\n"
        f"Setting: {scene.setting}\n\n"
        f"Sources:\n{_format_sources(sources)}"
    )
    out = await run_agent(build_fandom(), prompt)
    claim.precedent = str(out.get("precedent", ""))
    claim.reasoning = str(out.get("reasoning", ""))
    # A flashpoint with documented precedent is contested by definition: people
    # are actively arguing about it. That is an empirical call, not a judgement.
    claim.verdict = (
        Verdict.CONTESTED if out.get("is_flashpoint") else Verdict.VERIFIED
    )


async def _check_rights(claim: Claim, scene: Scene) -> None:
    # Clearance is a different question from accuracy: a real 1963 song is
    # historically perfect and still needs a sync licence.
    objective = (
        f"Establish the rights position for using this in a production: "
        f"{claim.text}. Who controls it, and is permission or a licence needed?"
    )
    sources = await parallel_client.search(objective)
    claim.sources = sources

    if not sources:
        claim.verdict = Verdict.UNVERIFIABLE
        claim.rights_status = "unknown"
        claim.reasoning = "No sources on the rights position. Never assume it is free to use."
        claim.rights_action = "Refer to the clearance desk before use."
        return

    prompt = (
        f"Element: {claim.text}\n"
        f"Production: {scene.project} ({scene.mode.value})\n\n"
        f"Sources:\n{_format_sources(sources)}"
    )
    out = await run_agent(build_rights(), prompt)
    claim.rights_status = str(out.get("status", "unknown"))
    claim.rights_action = str(out.get("action", ""))
    claim.reasoning = str(out.get("reasoning", ""))
    # Exposure is not a factual error, so it must not be reported as one. Only
    # "no obstacle found" passes; everything else needs a person.
    claim.verdict = (
        Verdict.VERIFIED
        if claim.rights_status == "no_obstacle_found"
        else Verdict.CONTRADICTED
        if claim.rights_status == "licence_required"
        else Verdict.CONTESTED
        if claim.rights_status == "restricted"
        else Verdict.UNVERIFIABLE
    )


async def _check_continuity(scene: Scene, tracker: RunTracker | None) -> None:
    """Canon claims, checked against the production bible and nothing else."""
    canon = [c for c in scene.claims if c.kind == ClaimKind.CANON]

    async with _step(tracker, "continuity") as step:
        if not canon:
            _skip(step, "no canon claims in this scene")
            return
        if not scene.bible.strip():
            for claim in canon:
                claim.verdict = Verdict.UNVERIFIABLE
                claim.reasoning = (
                    "No production bible supplied, so internal canon cannot be checked."
                )
            _skip(step, f"{len(canon)} canon claims, but no bible for this production")
            return

        prompt = (
            f"Production bible:\n{scene.bible}\n\n"
            f"Claims from the scene:\n"
            + "\n".join(f"- {c.text}" for c in canon)
        )
        out = await run_agent(build_continuity(), prompt)
        conflicts = out.get("conflicts") or []

        for raw in conflicts:
            text = str(raw.get("claim_text", "")).strip().lower()
            match = next(
                (c for c in canon if text and (text in c.text.lower() or c.text.lower() in text)),
                None,
            )
            if match is None:
                continue
            match.verdict = Verdict.CONTRADICTED
            match.bible_says = str(raw.get("bible_says", ""))
            match.reasoning = str(raw.get("reasoning", ""))

        for claim in canon:
            if claim.verdict is None:
                claim.verdict = Verdict.VERIFIED
                claim.reasoning = "Consistent with the production bible."

        _detail(
            step,
            f"{len(conflicts)} conflict(s) across {len(canon)} canon claims"
            if conflicts
            else f"{len(canon)} canon claims consistent with the bible",
        )


async def _adjudicate(scene: Scene, tracker: RunTracker | None) -> None:
    """Apply the escalation rule, then write handoff notes for contested claims.

    The rule is `adjudicator.route` — a pure function. The model is used only to
    write the note, never to decide whether the note is needed.
    """
    async with _step(tracker, "adjudicator") as step:
        for claim in scene.claims:
            claim.needs_human, claim.escalation_reason = route(claim, scene.mode)

        contested = [
            c for c in scene.claims if c.verdict == Verdict.CONTESTED and c.needs_human
        ]

        async def write_note(claim: Claim) -> None:
            out = await run_agent(
                build_adjudicator(),
                f"Claim: {claim.text}\n"
                f"What the check found: {claim.reasoning}\n\n"
                f"Sources:\n{_format_sources(claim.sources)}",
            )
            summary = str(out.get("summary", "")).strip()
            disputed = str(out.get("what_is_disputed", "")).strip()
            claim.handoff = "\n\n".join(p for p in (summary, disputed) if p)

        if contested:
            await asyncio.gather(*(write_note(c) for c in contested))

        queued = sum(1 for c in scene.claims if c.needs_human)
        _detail(
            step,
            f"{queued} of {len(scene.claims)} claims routed to a human"
            if queued
            else "nothing needs a human",
        )


async def check_claims(scene: Scene, tracker: RunTracker | None = None) -> Scene:
    """Step 3: check every claim, then decide what a human must see.

    Claims are independent, so the three checking agents run concurrently and
    their claims run concurrently within each — a scene has 3-8 claims and doing
    this serially would triple the wait for nothing. Adjudication runs last
    because it needs every verdict in.
    """
    if not scene.claims:
        scene.claims = await extract_claims(scene, tracker)

    # The check phase runs as an ADK graph: continuity, then a runtime-sized
    # fan-out of one child node per claim, then adjudication. The width is a
    # property of the scene and is not known until the Extractor has run, which
    # is what dynamic nodes exist for.
    mcp_toolset = parallel_mcp.build_search_toolset()

    async def fandom_check(claim: Claim, sc: Scene) -> None:
        # The Fandom agent gets Parallel's MCP tools when available; the
        # Verifier never does — it must not choose the evidence it is judged on.
        if mcp_toolset is not None:
            await _check_fandom_via_mcp(claim, sc, mcp_toolset)
        else:
            await _check_fandom(claim, sc)

    workflow = build_check_workflow(
        scene=scene,
        checkers={
            "verifier": _check_factual,
            "fandom": fandom_check,
            "rights": _check_rights,
        },
        continuity=lambda: _check_continuity(scene, tracker),
        adjudicate=lambda: _adjudicate(scene, tracker),
        step=lambda name: _step(tracker, name),
        note=lambda name, detail: tracker.note(name, detail) if tracker else None,
    )
    await run_agent_state(workflow, scene.id)


    get_ledger().save_scene(scene)
    return scene


async def decide(
    scene: Scene,
    claim_id: str,
    disposition: Disposition,
    rationale: str,
    decided_by: str = "writer",
    tracker: RunTracker | None = None,
) -> Scene:
    """Step 4: the human decision, and the revision it triggers.

    `fixed` rewrites the scene and re-checks it — a correction must not be able
    to introduce a new error silently. `keep_deliberate` leaves the scene alone
    and records the choice, which is the whole point of the product.
    """
    claim = next((c for c in scene.claims if c.id == claim_id), None)
    if claim is None:
        return scene

    claim.disposition = disposition
    claim.rationale = rationale
    claim.decided_by = decided_by

    ledger = get_ledger()

    if disposition == Disposition.FIXED:
        async with _step(tracker, "writer") as step:
            # Revise, judge the revision, and go round once more if it missed.
            # Accepting the first non-empty rewrite meant a revision that changed
            # the wording but not the fact was passed straight into another full
            # round of live checking, on the writer's time.
            workflow, outcome = build_revise_workflow(
                claim=claim.text,
                finding=claim.reasoning,
                bible_says=claim.bible_says,
            )
            await run_agent_state(workflow, scene.text)
            new_text = outcome["text"].strip()
            verdict = outcome["verdict"]
            attempts = outcome["attempts"] or 1
            if not new_text:
                _detail(step, "no revision produced")
            else:
                what = outcome["what_changed"] or "revised the scene"
                # Say when the critic was still unhappy. A revision that ran out
                # of attempts is worth knowing about, not worth hiding.
                suffix = (
                    f" (critic unsatisfied after {attempts})"
                    if verdict == "not_fixed"
                    else f" (accepted on attempt {attempts})"
                    if attempts > 1
                    else ""
                )
                _detail(step, f"{what}{suffix}")
            if verdict == "not_fixed":
                logger.info("Revision accepted after the critic ran out of attempts")
        if new_text:
            scene.text = new_text
            scene.revision += 1
            what = f"Corrected: {claim.text}"
            # Re-check: the fix may have introduced something new.
            scene.claims = await extract_claims(scene, tracker)
            await check_claims(scene, tracker)
        else:
            what = f"Correction attempted but no revision produced: {claim.text}"
    elif disposition == Disposition.KEEP_DELIBERATE:
        what = f"Kept as deliberate: {claim.text}"
    else:
        what = f"Escalated to a human: {claim.text}"

    ledger.append_revision(
        RevisionEntry(
            revision=scene.revision,
            scene_id=scene.id,
            claim_id=claim.id,
            what_changed=what,
            why=rationale or "(no rationale given)",
            disposition=disposition,
            sources=claim.sources,
        )
    )
    ledger.save_scene(scene)
    return scene


def _format_sources(sources: list[Source]) -> str:
    return "\n\n".join(
        f"[{i + 1}] {s.title}\n{s.url}\n{s.snippet}" for i, s in enumerate(sources)
    )


def _parse_verdict(value: object) -> Verdict:
    try:
        return Verdict(str(value).lower().strip())
    except ValueError:
        return Verdict.UNVERIFIABLE
