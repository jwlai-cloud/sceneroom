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

"""Revise, judge, and go round again — as an ADK graph Workflow.

This replaces the `LoopAgent` version. ADK deprecates `LoopAgent` in favour of
the graph API, and the graph turns out to suit this codebase better than the
loop did, for a reason that is not about deprecation:

**The routing decision is a plain function, not a model.** The docs describe the
graph API as "switching between non-deterministic AI-powered agents and
deterministic code as needed", and that is the same argument as ADR 002 — the
model judges, code decides what happens next.

    START -> prepare -> reviser -> stash -> critic -> route
                 ^                                      |
                 +---------------- "retry" -------------+

`prepare`, `stash` and `route` are ordinary Python. Only `reviser` and `critic`
are models. `route` emits `Event(route=["retry"])` to go round again; emitting
anything with no matching edge ends the branch, which is how the graph stops.

The claim and the finding travel in a closure rather than in session state: the
workflow is built per decision, so they are constants for its whole life, and a
closure cannot drift the way a shared state key can.

Still model-only — nothing here searches. The graph asks "did you do what you
said"; the real verification runs afterwards against Parallel. A model must not
mark its own homework as verified.
"""

from __future__ import annotations

import logging

from google.adk import Agent, Event, Workflow
from pydantic import BaseModel, Field

from app.config import MODEL

logger = logging.getLogger(__name__)

# Two passes is the whole budget. If the second attempt has not landed the
# correction, a third will not, and the writer is waiting.
MAX_ATTEMPTS = 2


class ReviseTask(BaseModel):
    scene: str = Field(description="The scene as it currently stands.")
    claim: str = Field(description="The flagged claim to correct.")
    finding: str = Field(description="What the sources establish instead.")
    bible_says: str = Field(default="", description="Production canon, if any.")
    previous_reason: str = Field(
        default="", description="Why the last attempt was rejected. Empty on the first."
    )


class Revision(BaseModel):
    text: str = Field(description="The full scene, revised. Never a diff.")
    what_changed: str = Field(description="The specific change made, in one sentence.")


class CriticTask(BaseModel):
    scene: str
    claim: str
    finding: str


class Judgement(BaseModel):
    verdict: str = Field(description='Exactly "fixed" or "not_fixed".')
    reason: str = Field(description="One sentence. If not fixed, what is still wrong.")


REVISER_INSTRUCTION = """
You revise a scene to correct one specific factual problem, and change nothing
else.

You are given the scene, the flagged claim, and what the sources establish. If
`previous_reason` is not empty, your last attempt was rejected for that reason —
read it and do what it says.

Rules:
- Return the complete scene, not a diff and not only the changed lines.
- Change as little as possible. Keep the writer's voice, rhythm and blocking.
- Fix the fact, not the paragraph around it.
- Never resolve the problem by deleting the moment. Removing the detail is
  giving up, not correcting.
""".strip()


CRITIC_INSTRUCTION = """
You check whether a revision actually corrected the problem it was meant to.

You are given the revised scene, the flagged claim, and what the sources
establish. Decide one thing: is that specific problem gone?

- "fixed"     — the scene no longer makes the claim, and the correction matches
                what the sources establish.
- "not_fixed" — the claim survives, or the wording changed without the fact
                changing, or the moment was deleted rather than corrected. Say
                precisely what is still wrong; the next attempt is given your
                reason.

Be strict. A revision that is merely different is not a revision that is
correct, and passing one costs the writer another full round of checking.

Answer with exactly "fixed" or "not_fixed" — nothing else, no capitals, no
punctuation. A different wording routes the graph wrongly.
""".strip()


# --- the deterministic parts, as pure functions -----------------------------
#
# The graph wraps these; it does not hide them. Routing is the decision this
# whole design turns on (ADR 002), so it has to be reachable and testable
# without standing a graph up or reaching into ADK's node internals.


def normalise_verdict(raw: str) -> str:
    """Map whatever the model said onto exactly one of two routes.

    A route key is matched exactly. The model answered "Not Fixed" once against
    a "not_fixed" edge, no edge matched, and the branch ended silently — the
    retry was lost and nothing said so.
    """
    return "fixed" if str(raw).strip().lower().replace(" ", "_") == "fixed" else "not_fixed"


def decide_route(result: dict, judged: Judgement) -> str:
    """Record the judgement and say which edge to take."""
    result["attempts"] += 1
    result["verdict"] = normalise_verdict(judged.verdict)
    result["reason"] = judged.reason
    retry = result["verdict"] == "not_fixed" and result["attempts"] < MAX_ATTEMPTS
    return "retry" if retry else "done"


def next_task(
    result: dict, scene: str, claim: str, finding: str, bible_says: str = ""
) -> ReviseTask:
    """Build the reviser's input, carrying any rejection forward.

    A critic that says "no" is useless if the reviser never hears why.
    """
    return ReviseTask(
        scene=result["text"] or str(scene),
        claim=claim,
        finding=finding,
        bible_says=bible_says,
        previous_reason=result["reason"] if result["verdict"] == "not_fixed" else "",
    )


def _as(model: type[BaseModel], value: object) -> BaseModel:
    """Node input arrives typed, or as a dict, depending on the producer."""
    if isinstance(value, model):
        return value
    if isinstance(value, dict):
        return model.model_validate(value)
    return model.model_validate_json(str(value))


def build_revise_workflow(
    claim: str, finding: str, bible_says: str = ""
) -> tuple[Workflow, dict]:
    """A workflow for one correction, and the dict its result lands in.

    Built per decision so the claim and finding can live in a closure. The
    returned dict is filled in as the graph runs — read it after.
    """
    result: dict = {
        "text": "", "what_changed": "", "verdict": "", "reason": "", "attempts": 0,
    }

    def prepare(node_input: str) -> ReviseTask:
        # First pass gets the scene as workflow input; a retry re-reads whatever
        # the last attempt produced, plus the critic's reason for rejecting it.
        return next_task(result, node_input, claim, finding, bible_says)

    reviser = Agent(
        name="reviser",
        model=MODEL,
        description="Rewrites the scene to correct one flagged claim.",
        instruction=REVISER_INSTRUCTION,
        input_schema=ReviseTask,
        output_schema=Revision,
    )

    def stash(node_input: Revision) -> CriticTask:
        rev = _as(Revision, node_input)
        result["text"] = rev.text
        result["what_changed"] = rev.what_changed
        return CriticTask(scene=rev.text, claim=claim, finding=finding)

    critic = Agent(
        name="revision_critic",
        model=MODEL,
        description="Decides whether the revision actually landed the correction.",
        instruction=CRITIC_INSTRUCTION,
        input_schema=CriticTask,
        output_schema=Judgement,
    )

    def route(node_input: Judgement) -> Event:
        return Event(route=[decide_route(result, _as(Judgement, node_input))])

    def finish(node_input: object) -> Event:
        """Terminal node for the accepted route.

        A route with no edge also ends the branch, but ADK logs a warning every
        time — noise on the successful path. An explicit end says the graph
        finished on purpose.
        """
        return Event(message=result["what_changed"] or "no revision produced")

    workflow = Workflow(
        name="revise_until_fixed",
        description="Revise the scene, judge the revision, and retry once if it missed.",
        edges=[
            ("START", prepare, reviser, stash, critic, route),
            (route, {"retry": prepare, "done": finish}),
        ],
    )
    return workflow, result
