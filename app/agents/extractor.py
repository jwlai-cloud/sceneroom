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

"""Extractor — pulls checkable claims out of a scene.

Recall matters more than precision here: a claim that is never extracted can
never be checked, and that is exactly the failure mode the product exists to
prevent.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from app.config import MODEL


class ExtractedClaim(BaseModel):
    kind: str = Field(
        description="One of: factual, historical, canon, rights, fandom."
    )
    text: str = Field(description="The claim stated plainly, checkable on its own.")
    excerpt: str = Field(description="The span of scene text it came from.")


class ExtractedClaims(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


INSTRUCTION = """
You are a researcher preparing a scene for verification. Pull out every
assertion that could be checked against the real world.

Extract claims of these kinds:
- factual     — a checkable statement about the world
- historical  — period accuracy: technology, dress, language, customs, events
- canon       — a detail the production's own bible speaks to. Only use this
                when a bible is supplied below and actually mentions the
                subject: a character's weapon, a location's layout, what was
                established in an earlier episode. Checked against the bible,
                never against the web.
- rights      — named music, footage, trademarks, real people's likenesses
- fandom      — subject matter this audience is known to scrutinise closely,
                especially anything politically or culturally sensitive

Rules:
- State each claim so it can be checked standing alone, without the scene.
  Bad: "the radio". Good: "A Seoul detective in 1963 would carry a portable
  two-way radio of this size."
- Quote the exact span of scene text it came from as the excerpt.
- Favour recall. A claim you skip is a claim nobody checks. If in doubt,
  extract it.
- Do not extract pure emotion, blocking, or dialogue subtext — those aren't
  checkable.
- Aim for 3-8 claims on a typical scene.

If a production bible is supplied, read it first and extract a `canon` claim
for every scene detail it speaks to — whether the scene agrees with it or not.
Agreement still needs checking; that is the whole point of continuity. If no
bible is supplied, never use `canon`.

Always consider whether a `fandom` claim applies. Any scene touching a real
historical period, a real people, a contested territory, a religion, or a
figure who actually lived carries audience-sensitivity risk — extract that as a
`fandom` claim even when the writing itself looks innocuous. This is the
category most easily missed, and the most expensive to miss.
""".strip()


def build_extractor() -> LlmAgent:
    return LlmAgent(
        name="extractor",
        model=MODEL,
        description="Extracts checkable claims from a scene.",
        instruction=INSTRUCTION,
        output_schema=ExtractedClaims,
        output_key="extracted_claims",
    )
