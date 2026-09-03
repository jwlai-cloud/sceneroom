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

"""One Imagen frame of the signed-off scene.

The demo's full stop, and deliberately the smallest thing here. Everything else
in this product is text — a script page, flag cards, citations, a ledger — which
is right, and monochrome. One frame closes the loop from intent to something you
could shoot.

Not a storyboard: one image, no variants, no shot grid, no board. Image
generation is the crowded lane and we are not competing in it (CLAUDE.md).

The frame is a payoff, not provenance, so it is never written to the ledger. It
is generated on demand and handed straight to the browser, which also keeps a
megabyte of base64 out of every scene snapshot in BigQuery.
"""

from __future__ import annotations

import base64
import logging

from app.config import IMAGE_MODEL, LOCATION, PROJECT_ID
from app.models import Scene

logger = logging.getLogger(__name__)

# Checked against the models this project can actually see, not against the
# docs: `imagen-*` publisher models are not available here and returned 404 in
# every region tried. The Gemini image models are, and `generate_images` is
# deprecated in favour of `generate_content` regardless, so this uses that.
IMAGE_LOCATION = LOCATION


def _prompt(scene: Scene) -> str:
    """Describe the frame from the scene the writer signed off, not the brief.

    It has to be the corrected text: the whole point is that this is the scene
    *after* every flag was decided.
    """
    body = scene.text.strip()[:1500]
    return (
        "A single cinematic film still, as a director of photography would frame "
        "the opening shot of this scene. Photographic, naturalistic lighting, "
        "shallow depth of field, 35mm. No text, no captions, no watermarks, no "
        "on-screen writing.\n\n"
        f"Period and place: {scene.setting or 'unspecified'}.\n\n"
        f"Scene:\n{body}"
    )


async def render(scene: Scene) -> str | None:
    """Return the frame as a data URL, or None if it could not be made.

    None is an acceptable outcome everywhere it is used: this is the first thing
    to cut if it misbehaves, and it must never take a run down with it.
    """
    if not scene.text.strip():
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=PROJECT_ID, location=IMAGE_LOCATION)
        result = await client.aio.models.generate_content(
            model=IMAGE_MODEL,
            contents=_prompt(scene),
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
    except Exception as exc:
        logger.warning("Frame generation failed: %s", exc)
        return None

    # The response carries the image inline among the parts; there is no
    # dedicated images field on this path.
    for candidate in result.candidates or []:
        for part in (candidate.content.parts if candidate.content else []) or []:
            blob = getattr(part, "inline_data", None)
            if blob and blob.data:
                mime = blob.mime_type or "image/png"
                return f"data:{mime};base64," + base64.b64encode(blob.data).decode()

    # Usually a safety filter. Say so plainly rather than retrying blindly.
    logger.warning("No image returned for scene %s", scene.id)
    return None
