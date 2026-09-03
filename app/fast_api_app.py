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

"""HTTP API + static hosting for the Sceneroom UI."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import pathlib
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import orchestrator
from app.config import ENABLE_IMAGE, ESCALATION_CONTACT, MODEL, PROJECT_ID
from app.models import Disposition, Mode, Scene
from app.services import frame as frame_service
from app.services import parallel_client, parallel_mcp
from app.services.ledger import get_ledger
from app.services.runs import CREW, RunTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sceneroom",
    description="An agentic scene room: write a scene, then hold it to account.",
)

FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"


class DraftRequest(BaseModel):
    intent: str = Field(min_length=3, max_length=2000)
    project: str = "untitled"
    setting: str = ""
    mode: Mode = Mode.FICTION
    bible: str = Field(
        default="",
        max_length=20_000,
        description="Production bible. The Continuity agent checks canon against it.",
    )


class DecisionRequest(BaseModel):
    claim_id: str
    disposition: Disposition
    rationale: str = ""
    decided_by: str = "writer"


# --- access gate ------------------------------------------------------------
#
# The URL is public for ~9 weeks of judging, and every run behind it spends real
# money on Gemini and Parallel. This is a spend gate, not a security boundary:
# there is nothing here worth stealing, only something worth billing.
#
# A cookie rather than a query parameter, because EventSource cannot set headers
# and a code in the URL would be written to every Cloud Run request log.
#
# Unset SCENEROOM_ACCESS_CODE leaves the service open, which is what local
# development and the tests use.

ACCESS_CODE = os.getenv("SCENEROOM_ACCESS_CODE", "")
ACCESS_COOKIE = "sr_access"


class AccessRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200)


def require_access(request: Request) -> None:
    """Reject a request that has not presented the access code."""
    if not ACCESS_CODE:
        return
    presented = request.cookies.get(ACCESS_COOKIE, "")
    if not hmac.compare_digest(presented, ACCESS_CODE):
        raise HTTPException(401, "This demo needs an access code.")


@app.get("/api/access")
def access_state(request: Request) -> dict:
    """Whether a code is needed, and whether this browser already has it."""
    if not ACCESS_CODE:
        return {"required": False, "unlocked": True}
    unlocked = hmac.compare_digest(request.cookies.get(ACCESS_COOKIE, ""), ACCESS_CODE)
    return {"required": True, "unlocked": unlocked}


@app.post("/api/access")
def unlock(req: AccessRequest, response: Response) -> dict:
    if not ACCESS_CODE:
        return {"unlocked": True}
    if not hmac.compare_digest(req.code.strip(), ACCESS_CODE):
        # Deliberately no detail about why. Same message, every failure.
        raise HTTPException(401, "That code was not recognised.")
    response.set_cookie(
        ACCESS_COOKIE,
        ACCESS_CODE,
        max_age=60 * 60 * 24 * 90,  # past the judging window
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"unlocked": True}


@app.get("/api/health")
def health() -> dict:
    """Also surfaces whether Parallel is live, so a demo can never pass off
    fixture data as real search without saying so."""
    return {
        "status": "ok",
        "model": MODEL,
        "project": PROJECT_ID or None,
        "parallel_live": parallel_client.is_live(),
        "parallel_mcp": parallel_mcp.is_live(),
        "ledger": get_ledger().backend,
        "ledger_target": get_ledger().target,
        "image_enabled": ENABLE_IMAGE,
        "escalation_contact": ESCALATION_CONTACT,
    }


@app.post("/api/scenes", dependencies=[Depends(require_access)])
async def create_scene(req: DraftRequest) -> Scene:
    """Draft a scene, then extract and check every claim in it."""
    scene = await orchestrator.draft_scene(
        intent=req.intent,
        project=req.project,
        mode=req.mode,
        setting=req.setting,
        bible=req.bible,
    )
    if not scene.text:
        raise HTTPException(502, "Scene drafting failed — check model credentials.")
    return await orchestrator.check_claims(scene)


@app.post("/api/scenes/demo", dependencies=[Depends(require_access)])
async def create_demo_scene() -> Scene:
    """Load the pinned sample scene. Lets the full loop be demonstrated with no
    API keys; the UI labels it as sample data."""
    return await orchestrator.load_demo_scene()


@app.get("/api/scenes")
def list_scenes() -> list[Scene]:
    return get_ledger().list_scenes()


@app.get("/api/scenes/{scene_id}")
def get_scene(scene_id: str) -> Scene:
    scene = get_ledger().get_scene(scene_id)
    if scene is None:
        raise HTTPException(404, "No such scene.")
    return scene


@app.post("/api/scenes/{scene_id}/decide", dependencies=[Depends(require_access)])
async def decide(scene_id: str, req: DecisionRequest) -> Scene:
    """Record the human's decision on one flag, and revise if they chose to fix."""
    scene = get_ledger().get_scene(scene_id)
    if scene is None:
        raise HTTPException(404, "No such scene.")
    if req.disposition == Disposition.KEEP_DELIBERATE and not req.rationale.strip():
        # The rationale is the product. Keeping something deliberately without
        # saying why defeats the entire audit trail.
        raise HTTPException(400, "A rationale is required to keep this deliberately.")
    return await orchestrator.decide(
        scene=scene,
        claim_id=req.claim_id,
        disposition=req.disposition,
        rationale=req.rationale,
        decided_by=req.decided_by,
    )


@app.post("/api/scenes/{scene_id}/frame", dependencies=[Depends(require_access)])
async def scene_frame(scene_id: str) -> dict:
    """One Imagen frame of the signed-off scene — the demo's full stop.

    Returned straight to the browser rather than stored: the frame is a payoff,
    not provenance, and a megabyte of base64 has no business in the ledger.
    """
    if not ENABLE_IMAGE:
        raise HTTPException(404, "Image generation is switched off.")
    scene = get_ledger().get_scene(scene_id)
    if scene is None:
        raise HTTPException(404, "No such scene.")
    if scene.open_flags:
        # The frame is of the scene that was signed off. Rendering one with
        # flags still open would picture a scene nobody approved.
        raise HTTPException(409, "Decide the open flags first — the frame is of the signed-off scene.")
    data_url = await frame_service.render(scene)
    if data_url is None:
        raise HTTPException(502, "The frame could not be rendered.")
    return {"frame": data_url}


@app.get("/api/scenes/{scene_id}/provenance")
def provenance(scene_id: str) -> list:
    """The audit trail: what was checked, decided, and why."""
    return get_ledger().revisions(scene_id)


@app.get("/api/scenes/{scene_id}/record.md")
def provenance_record(scene_id: str) -> PlainTextResponse:
    """The provenance record, as a document a person can send.

    This is the artefact the pitch describes: what was checked, against which
    source, decided by whom, and why. A JSON endpoint is for machines; when a
    controversy lands somebody has to send a *file* to a lawyer or a broadcaster,
    so it renders as Markdown.
    """
    scene = get_ledger().get_scene(scene_id)
    if scene is None:
        raise HTTPException(404, "No such scene.")
    revisions = get_ledger().revisions(scene_id)

    out = [
        f"# Provenance record — {scene.setting or scene.project}",
        "",
        f"- Scene `{scene.id}`, revision {scene.revision}",
        f"- Production type: **{scene.mode.value}**",
        f"- Brief: {scene.intent}",
        f"- Claims checked: {len(scene.claims)}",
        "",
        "## Claims",
        "",
    ]
    for i, c in enumerate(scene.claims, 1):
        out += [
            f"### {i}. {c.text}",
            "",
            f"- Kind: {c.kind.value} · Verdict: **{c.verdict.value if c.verdict else 'unchecked'}**",
            f"- Decision: **{c.disposition.value.replace('_', ' ')}**"
            + (f" — {c.rationale}" if c.rationale else ""),
        ]
        if c.needs_human and c.disposition == Disposition.PENDING:
            out.append(f"- **Awaiting a human:** {c.escalation_reason}")
        if c.reasoning:
            out.append(f"- Finding: {c.reasoning}")
        if c.rights_action:
            out.append(f"- Clearance ({c.rights_status}): {c.rights_action}")
        if c.precedent:
            out.append(f"- Precedent: {c.precedent}")
        if c.sources:
            out += ["- Sources:"] + [f"    - [{s.title}]({s.url})" for s in c.sources]
        out.append("")

    out += ["## Ledger", "", "| rev | what changed | why | decision |", "|---|---|---|---|"]
    for r in revisions:
        decision = r.disposition.value.replace("_", " ") if r.disposition else "—"
        out.append(
            f"| {r.revision} | {r.what_changed} | {r.why} | {decision} |"
        )
    out += ["", "## The scene as it stands", "", "```", scene.text, "```", ""]
    out.append(
        "_Sceneroom does not guarantee correctness. It records that no claim "
        "shipped unreviewed._"
    )

    return PlainTextResponse(
        "\n".join(out),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{scene_id}-record.md"'},
    )


# --- Streaming: the crew, while it works ------------------------------------
#
# A full pass takes ~30s. Streamed as SSE rather than polled: polling needs a
# shared run store, and Cloud Run spreads polls across instances, so a poll
# would often hit an instance that never saw the run. One connection stays with
# the instance doing the work.
#
# EventSource can only issue GETs, so the brief arrives as query parameters.


def _sse(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(payload))}\n\n"


async def _stream(make_work: Callable[[RunTracker], Awaitable[Scene]]) -> StreamingResponse:
    tracker = RunTracker()

    async def run() -> Scene:
        try:
            return await make_work(tracker)
        finally:
            # Always close, or the client waits on a stream nobody will feed.
            tracker.close()

    async def events() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        # The crew up front, so the UI can show every agent as pending
        # immediately instead of growing a list as results trickle in.
        yield _sse("crew", {"agents": CREW})
        try:
            async for step in tracker.drain():
                yield _sse("step", step)
            scene = await task
            yield _sse("scene", scene)
        except Exception as exc:
            logger.exception("Streamed run failed")
            task.cancel()
            yield _sse("error", {"message": str(exc) or type(exc).__name__})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Deliberately not /api/scenes/stream: FastAPI matches routes in declaration
# order, so "stream" would be captured by /api/scenes/{scene_id} above and
# 404 as a missing scene. Verified — it did exactly that.
@app.get("/api/stream/scene", dependencies=[Depends(require_access)])
async def create_scene_stream(
    intent: str,
    project: str = "untitled",
    setting: str = "",
    mode: Mode = Mode.FICTION,
    bible: str = "",
) -> StreamingResponse:
    """Draft and check a scene, reporting each agent as it runs."""

    async def work(tracker: RunTracker) -> Scene:
        scene = await orchestrator.draft_scene(
            intent=intent,
            project=project,
            mode=mode,
            setting=setting,
            bible=bible,
            tracker=tracker,
        )
        if not scene.text:
            raise RuntimeError("Scene drafting failed — check model credentials.")
        return await orchestrator.check_claims(scene, tracker)

    return await _stream(work)


@app.get("/api/stream/scenes/{scene_id}/decide", dependencies=[Depends(require_access)])
async def decide_stream(
    scene_id: str,
    claim_id: str,
    disposition: Disposition,
    rationale: str = "",
    decided_by: str = "writer",
) -> StreamingResponse:
    """Record a decision. `fixed` revises and re-checks, so it streams too."""
    scene = get_ledger().get_scene(scene_id)
    if scene is None:
        raise HTTPException(404, "No such scene.")
    if disposition == Disposition.KEEP_DELIBERATE and not rationale.strip():
        raise HTTPException(400, "A rationale is required to keep this deliberately.")

    async def work(tracker: RunTracker) -> Scene:
        return await orchestrator.decide(
            scene=scene,
            claim_id=claim_id,
            disposition=disposition,
            rationale=rationale,
            decided_by=decided_by,
            tracker=tracker,
        )

    return await _stream(work)


# --- static UI --------------------------------------------------------------

if FRONTEND.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(FRONTEND / "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
