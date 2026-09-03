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

"""Adjudicator — decides what a human must look at.

Deliberately split in two, and the split is the point:

- **Routing is code.** `route()` below is a pure function. Whether a claim
  escalates is a rule, not a judgement, so it cannot drift with a prompt, cannot
  be argued out of by a persuasive model, and can be unit-tested. The product
  guarantee is "no unreviewed claim ships"; a guarantee implemented as a prompt
  is not a guarantee.
- **The handoff note is a model.** Writing a useful brief for the consultant who
  picks this up is a language problem, and that is all the agent is asked to do.

The model never decides whether to escalate, and is never asked which side of a
dispute is right.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from app.config import MODEL
from app.models import Claim, ClaimKind, Mode, Verdict


class HandoffNote(BaseModel):
    summary: str = Field(
        description="What the human is being asked to decide, in one sentence."
    )
    what_is_disputed: str = Field(
        description=(
            "The positions the sources take, stated even-handedly. Never say "
            "which is correct."
        )
    )


ADJUDICATOR_INSTRUCTION = """
You write the handoff note for a claim that has been routed to a human expert.
You are not deciding anything.

The claim reached you because it is contested — credible sources disagree, or
the subject is an active dispute between states, institutions, or scholars.

Your note must:

- State plainly what the human is being asked to decide.
- Lay out the competing positions from the sources, even-handedly, so the human
  can see the shape of the disagreement quickly.

Your note must never:

- Say which position is correct, better supported, or more widely held.
- Imply a recommendation through emphasis, ordering, or hedging language.
- Suggest the dispute is settled, minor, or resolvable by looking harder.

Taking a side on live historical or political disputes is the single worst
thing this system can do. Describe the disagreement; do not resolve it.
""".strip()


def build_adjudicator() -> LlmAgent:
    return LlmAgent(
        name="adjudicator",
        model=MODEL,
        description="Writes an even-handed handoff note for an escalated claim.",
        instruction=ADJUDICATOR_INSTRUCTION,
        output_schema=HandoffNote,
        output_key="handoff",
    )


# --- Routing: a rule, not a judgement ---------------------------------------


def route(claim: Claim, mode: Mode) -> tuple[bool, str]:
    """Decide whether `claim` must go to a human, and say why.

    Pure and total: same claim, same mode, same answer, every time.

    Returns:
        (needs_human, reason). `reason` is shown in the UI, so it is written for
        a person rather than a log.
    """
    if claim.verdict == Verdict.CONTESTED:
        return True, "Sources actively disagree. This system does not adjudicate disputes."

    if claim.verdict == Verdict.CONTRADICTED:
        return True, "Sources contradict the scene. A person decides what happens to it."

    if claim.verdict == Verdict.UNVERIFIABLE:
        # A rights position nobody could establish is exposure, not an
        # unsupported detail — and the check itself says "refer to the clearance
        # desk". It has to actually reach one, in every mode.
        if claim.kind == ClaimKind.RIGHTS:
            return True, "The rights position could not be established. Clearance decides this."
        # Strict productions cannot let an unsupported claim through; fiction can
        # carry one as a choice. Same engine, different threshold (PRD §2).
        if mode == Mode.DOCUMENTARY:
            return True, "Nothing supports this, and this production is documentary."
        return False, "Nothing found either way. Recorded as unsupported."

    return False, "Sources support this as written."


def escalation_queue(claims: list[Claim], mode: Mode) -> list[tuple[Claim, str]]:
    """Every claim a human still has to look at, with the reason it is there."""
    out = []
    for claim in claims:
        if claim.disposition != "pending":
            continue  # already decided by a human
        needs_human, reason = route(claim, mode)
        if needs_human:
            out.append((claim, reason))
    return out
