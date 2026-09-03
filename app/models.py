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

"""Domain model for Sceneroom.

The whole product turns on one idea: a deviation from reality is only a problem
when nobody decided to make it. So a Claim carries not just a verdict but a
*disposition* — what the human chose to do about it — and both are recorded.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Verdict(StrEnum):
    """What checking the claim established. Set by the agents."""

    VERIFIED = "verified"          # sources agree with the scene
    CONTRADICTED = "contradicted"  # sources disagree with the scene
    CONTESTED = "contested"        # sources actively disagree with each other
    UNVERIFIABLE = "unverifiable"  # nothing solid found either way


class Disposition(StrEnum):
    """What the human decided. Set by the writer, never by an agent.

    KEEP_DELIBERATE is the one that matters: it is how artistic licence is
    recorded as a choice rather than treated as an error.
    """

    PENDING = "pending"
    FIXED = "fixed"
    KEEP_DELIBERATE = "keep_deliberate"
    ESCALATED = "escalated"


class ClaimKind(StrEnum):
    FACTUAL = "factual"        # verifiable statement about the world
    HISTORICAL = "historical"  # period accuracy
    CANON = "canon"            # internal consistency with the production bible
    RIGHTS = "rights"          # music, trademark, likeness, footage
    FANDOM = "fandom"          # audience flashpoint, not necessarily an error


class Mode(StrEnum):
    """Per-project strictness. Same engine, different threshold."""

    DOCUMENTARY = "documentary"  # a deviation is an error until justified
    FICTION = "fiction"          # a deviation is a choice to be logged


class Source(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class Claim(BaseModel):
    """One checkable assertion pulled out of a scene."""

    id: str
    kind: ClaimKind
    text: str = Field(description="The claim, stated plainly.")
    excerpt: str = Field(default="", description="The span of scene text it came from.")

    verdict: Verdict | None = None
    reasoning: str = ""
    sources: list[Source] = Field(default_factory=list)

    # Fandom agent: precedent, not prediction. Empty for non-fandom claims.
    precedent: str = ""

    disposition: Disposition = Disposition.PENDING
    decided_by: str = ""
    rationale: str = Field(
        default="",
        description="Why the human decided this. Required for keep_deliberate.",
    )

    # Rights agent. Never "cleared" — this system surfaces exposure, it does not
    # clear anything. See agents/rights.py.
    rights_status: str = ""
    rights_action: str = ""

    # Continuity agent: what the production bible says instead, quoted.
    bible_says: str = ""

    # Adjudicator. `escalation_reason` is set by a pure rule (adjudicator.route),
    # never by a model. `handoff` is the model-written brief for the human, and
    # exists only for contested claims.
    needs_human: bool = False
    escalation_reason: str = ""
    handoff: str = ""

    @property
    def needs_attention(self) -> bool:
        # `needs_human` is what the Adjudicator decided, and it escalates things
        # this list would otherwise miss — an unestablished rights position is
        # UNVERIFIABLE and still has to reach clearance. Without it, such a
        # claim stayed out of `open_flags`, so the scene read as signed off and
        # the frame endpoint would render it.
        return self.disposition == Disposition.PENDING and (
            self.needs_human or self.verdict in (Verdict.CONTRADICTED, Verdict.CONTESTED)
        )


class Scene(BaseModel):
    """The unit of work. One scene, not a screenplay."""

    id: str
    project: str = "untitled"
    mode: Mode = Mode.FICTION
    intent: str = Field(description="The writer's brief, in plain language.")
    setting: str = Field(default="", description="Period/place, e.g. 'Seoul, 1963'.")
    text: str = ""
    revision: int = 1
    claims: list[Claim] = Field(default_factory=list)
    frame_url: str = ""

    # The production bible: internal canon the Continuity agent checks against.
    # Plain text, because a real bible is prose and parsing it into a schema
    # would lose exactly the nuance continuity turns on.
    bible: str = ""

    @property
    def open_flags(self) -> list[Claim]:
        return [c for c in self.claims if c.needs_attention]

    @property
    def is_signed_off(self) -> bool:
        return bool(self.claims) and not self.open_flags


class RevisionEntry(BaseModel):
    """Append-only provenance. Never edited, never reordered."""

    revision: int
    scene_id: str
    what_changed: str
    why: str = Field(description="The rationale. Not optional — this is the point.")
    claim_id: str = ""
    disposition: Disposition | None = None
    sources: list[Source] = Field(default_factory=list)
