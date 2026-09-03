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

"""Continuity — the only agent that checks inward.

Every other agent asks whether the scene matches the world. This one asks
whether it matches the *production*: the bible, the episodes already written,
the decisions already made. Scenes get written out of order, so this is a real
failure mode and the web cannot help with it — the answer exists only in the
production's own documents.

It is deliberately unable to search. Grounding it in the bible and nothing else
is what stops it inventing canon that no writer ever agreed to.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from app.config import MODEL


class ContinuityConflict(BaseModel):
    claim_text: str = Field(description="The claim from the scene that conflicts.")
    bible_says: str = Field(description="What the bible establishes instead. Quote it.")
    reasoning: str = Field(description="One sentence on why these cannot both hold.")


class ContinuityResult(BaseModel):
    conflicts: list[ContinuityConflict] = Field(
        default_factory=list,
        description="Empty when the scene is consistent with the bible.",
    )
    checked: int = Field(default=0, description="How many claims were compared.")


CONTINUITY_INSTRUCTION = """
You check one scene against a production bible for internal consistency.

The bible is the only authority. You have no other source, and you must not use
general knowledge about the real world — that is another agent's job. A scene
detail that is historically wrong but matches the bible is not your concern.

Report a conflict only when the bible actually establishes something the scene
contradicts. Specifically:

- The bible says a character carries a revolver; the scene gives them an
  automatic. That is a conflict — quote the bible line.
- The bible is silent on what a character carries. That is NOT a conflict.
  Silence is not contradiction, and inventing canon from silence is worse than
  finding nothing.

If the bible is empty or says nothing relevant, return no conflicts. Returning
an empty list is a correct and common answer. Do not manufacture findings to
look useful.
""".strip()


def build_continuity() -> LlmAgent:
    return LlmAgent(
        name="continuity",
        model=MODEL,
        description="Checks scene claims against the production bible.",
        instruction=CONTINUITY_INSTRUCTION,
        output_schema=ContinuityResult,
        output_key="continuity_check",
    )
