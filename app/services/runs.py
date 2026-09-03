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

"""Run events — what the crew is doing, while it is doing it.

A full pass takes ~30s and the UI used to show one unchanging sentence for all
of it. These events turn that wait into the evidence: each agent reports when it
starts, how long it took, and what it actually found.

Delivered over SSE rather than a polled run registry. Polling needs a shared
store, and Cloud Run routes each poll independently across instances, so a poll
would often land on an instance that never saw the run. One streamed connection
stays with the instance doing the work, so there is no cross-instance state.

# ponytail: no persistence. A dropped connection loses the timeline, not the
# work — the orchestrator keeps running and the scene lands in the ledger.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from enum import StrEnum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class StepStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"  # nothing for this agent to do on this scene


class RunStep(BaseModel):
    """One agent's turn. `detail` is what it found, in the user's words."""

    agent: str
    status: StepStatus = StepStatus.RUNNING
    detail: str = ""
    ms: int = 0


# The crew, in execution order. The UI renders this before anything runs, so a
# step that never fires still shows as pending rather than vanishing.
CREW = [
    "writer",
    "extractor",
    "continuity",
    "verifier",
    "fandom",
    "rights",
    "adjudicator",
]


class RunTracker:
    """Collects step events and hands them to a streaming response.

    Every orchestrator entry point takes one of these, optionally. When it is
    None the orchestrator behaves exactly as before — the non-streaming API and
    the tests use that path.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[RunStep | None] = asyncio.Queue()
        self.steps: list[RunStep] = []

    @contextlib.asynccontextmanager
    async def step(self, agent: str) -> AsyncIterator[RunStep]:
        """Time one agent's turn and publish it, whatever happens.

        The caller sets `step.detail` to say what it found. A raised exception
        marks the step failed and re-raises — this never swallows errors.
        """
        step = RunStep(agent=agent, status=StepStatus.RUNNING)
        self.steps.append(step)
        self._publish(step)
        started = time.perf_counter()
        try:
            yield step
        except Exception as exc:
            step.status = StepStatus.FAILED
            step.detail = step.detail or f"{type(exc).__name__}"
            raise
        else:
            if step.status == StepStatus.RUNNING:
                step.status = StepStatus.DONE
        finally:
            step.ms = int((time.perf_counter() - started) * 1000)
            self._publish(step)

    def note(self, agent: str, detail: str) -> None:
        """Publish progress inside a long step, e.g. 'checked 4 of 7'."""
        self._publish(RunStep(agent=agent, status=StepStatus.RUNNING, detail=detail))

    def close(self) -> None:
        self._queue.put_nowait(None)

    def _publish(self, step: RunStep) -> None:
        # A copy, because the caller keeps mutating the live object.
        self._queue.put_nowait(step.model_copy())

    async def drain(self) -> AsyncIterator[RunStep]:
        """Yield steps until close() is called."""
        while True:
            step = await self._queue.get()
            if step is None:
                return
            yield step


class RunEnvelope(BaseModel):
    """What the stream emits. Exactly one of `step` or `scene` is set."""

    kind: str = Field(description="One of: step, scene, error.")
    step: RunStep | None = None
    scene: dict | None = None
    message: str = ""
