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

"""Verifier and Fandom — the two agents grounded in Parallel.

They ask different questions:

- **Verifier**: is this true? Evidence for or against the claim itself.
- **Fandom**:   will this audience object? What comparable productions were
                criticised for, whether or not the claim is factually fine.

Both are given sources and asked to judge only those sources. Neither is asked
to rule on a dispute: if the evidence itself disagrees, the verdict is
`contested` and a human decides.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from app.config import MODEL


class VerificationResult(BaseModel):
    verdict: str = Field(
        description="One of: verified, contradicted, contested, unverifiable."
    )
    reasoning: str = Field(description="One or two sentences, citing the sources.")


class FoundSource(BaseModel):
    title: str = Field(description="The page title, as found.")
    url: str = Field(description="The exact URL. Never a URL you did not open.")


class FandomResult(BaseModel):
    is_flashpoint: bool = Field(
        description="True if this audience is known to scrutinise or dispute this."
    )
    precedent: str = Field(
        description=(
            "What comparable productions were criticised for, with specifics. "
            "Empty string if no precedent was found."
        )
    )
    reasoning: str = Field(description="One or two sentences, citing the sources.")
    sources: list[FoundSource] = Field(
        default_factory=list,
        description=(
            "Only used when this agent searched for itself. Every source must be "
            "one it actually retrieved."
        ),
    )


VERIFIER_INSTRUCTION = """
You judge a single claim against a set of sources you are given. You do not use
prior knowledge as evidence — only what the sources say.

Choose exactly one verdict:

- verified      — the sources support the claim.
- contradicted  — the sources show the claim is wrong. Say what is actually
                  true, specifically, so it can be corrected.
- contested     — the sources genuinely disagree with each other, or the topic
                  is an active dispute between credible parties. Use this for
                  matters of contested historiography or politics. It is not a
                  fallback for "unsure".
- unverifiable  — no sources, or nothing that speaks to the claim. Never treat
                  absence of evidence as support.

Critical: when the topic is contested, your job is to say so — not to pick the
side you find more persuasive. Taking a position on a live historical or
political dispute is the single worst thing this system can do.

Before you answer `verified` or `contradicted`, check whether the question is
one specialists actually argue about. Attribution and authorship, who
originated something, the boundaries and allegiance of historical polities,
responsibility for events, and the motives of real people are disputed far more
often than they look. If reputable sources take different positions — even when
one is more common, more recent, or better argued — that is `contested`.

A majority view is not a settled question. Preferring the majority is exactly
the judgement this system refuses to make.

Watch the absolutes. When a claim about origination or authorship carries a
word like "alone", "personally", "unaided", "without help", "first" or "the
only", that qualifier is usually the disputed part, not incidental wording.
Sources describing other contributors do not make such a claim `contradicted` —
they are one side of the argument the claim takes a position on. That is
`contested`. Reserve `contradicted` for claims whose factual core fails: a
wrong date, a wrong place, an object that did not yet exist.

Keep the reasoning to one or two sentences, and refer to what the sources
actually said.
""".strip()


FANDOM_INSTRUCTION = """
You assess whether an audience is likely to object to something in a scene.

This is a different question from whether it is true. Something can be
factually correct and still be a flashpoint, and something can be a harmless
invention that nobody will care about.

You are given sources about how audiences and critics have responded to
comparable productions. Report **precedent, not prediction**: what has actually
drawn complaints before, with specifics — which kinds of production, what the
objection was, what the consequence was.

Good: "Several period dramas since 2023 drew formal complaints over depictions
touching this dispute; in some cases scenes were re-edited after broadcast."
Bad:  "Fans will probably be annoyed by this."

If the sources show no precedent, say so plainly and set is_flashpoint false.
Do not invent an audience reaction. Do not speculate about sentiment.
""".strip()


def build_verifier() -> LlmAgent:
    return LlmAgent(
        name="verifier",
        model=MODEL,
        description="Judges a claim against retrieved sources.",
        instruction=VERIFIER_INSTRUCTION,
        output_schema=VerificationResult,
        output_key="verification",
    )


FANDOM_MCP_INSTRUCTION = (
    FANDOM_INSTRUCTION
    + """

You have web_search and web_fetch. Use them — this question is not answerable
in one query. Work like a researcher:

1. Search for how productions set in this period have been received.
2. When a search result hints at a controversy, fetch that page and read what
   the objection actually was and what it cost the production.
3. Search again for what you learned, until you can state precedent concretely
   or are satisfied there is none.

Then fill `sources` with the pages you actually retrieved — never a URL you did
not open, and never one you assembled from memory. An invented citation is
worse than reporting that you found nothing.
"""
)


def build_fandom(tools: list | None = None) -> LlmAgent:
    """The Fandom agent, with Parallel's MCP tools when they are available.

    With tools it searches for itself, because finding precedent is iterative:
    a controversy is discovered, then read, then traced. Without them it judges
    sources the orchestrator retrieved. Same schema either way, so the rest of
    the system does not care which path ran.
    """
    return LlmAgent(
        name="fandom",
        model=MODEL,
        description="Assesses audience flashpoint risk from documented precedent.",
        instruction=FANDOM_MCP_INSTRUCTION if tools else FANDOM_INSTRUCTION,
        output_schema=FandomResult,
        output_key="fandom_check",
        tools=tools or [],
    )
