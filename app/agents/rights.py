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

"""Rights — clearance, which is a different question from truth.

The Verifier asks whether a detail is accurate. This asks whether using it costs
money or permission. Those come apart constantly: a real 1963 song is
historically perfect and still needs a sync licence; a trademark used on screen
can be accurate and still a problem.

Deliberately never says "cleared". Clearance is a lawyer's signature, not a
model's opinion, and a system that implies otherwise is worse than no system.
The most positive verdict here is "no obstacle found" — which routes to a human
anyway when anything is at stake.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from app.config import MODEL


class RightsResult(BaseModel):
    status: str = Field(
        description=(
            "One of: no_obstacle_found, licence_required, restricted, unknown. "
            "Never 'cleared' — this system does not clear rights."
        )
    )
    holder: str = Field(
        default="",
        description="Who appears to control it, if the sources name anyone.",
    )
    action: str = Field(
        description="What a production would have to do next, concretely."
    )
    reasoning: str = Field(description="One or two sentences, citing the sources.")


RIGHTS_INSTRUCTION = """
You assess rights exposure for one element of a scene — music, a trademark, a
brand, footage, or a real person's likeness — using only the sources given.

Choose exactly one status:

- no_obstacle_found  — the sources show nothing requiring permission. This is
                       the most positive verdict available to you.
- licence_required   — the sources indicate it is controlled and using it needs
                       permission or payment. Name the holder if the sources do.
- restricted         — beyond licensing: the sources show use is limited,
                       disputed, or carries a legal or reputational risk
                       (likeness of a living person, contested imagery).
- unknown            — the sources do not establish the position. Common and
                       acceptable. Never guess at rights.

You must never output "cleared", and never state that something is safe to use.
Clearance requires a human with authority to sign. Your job is to surface the
exposure and say what the production would have to do about it.

For `action`, be concrete and practical: "Obtain a sync licence from the
publisher before the mix is locked" beats "Consider legal review".
""".strip()


def build_rights() -> LlmAgent:
    return LlmAgent(
        name="rights",
        model=MODEL,
        description="Assesses licensing and clearance exposure from sources.",
        instruction=RIGHTS_INSTRUCTION,
        output_schema=RightsResult,
        output_key="rights_check",
    )
