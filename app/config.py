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

"""Runtime configuration."""

from __future__ import annotations

import os

import google.auth

# Vertex AI wiring. Auto-detects the project so local dev and Cloud Run agree.
try:
    _, _PROJECT = google.auth.default()
except Exception:  # no ADC locally — the API still serves, agents will error
    _PROJECT = None

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or (_PROJECT or "")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# Flash everywhere: the work is many small structured calls, not deep reasoning.
MODEL = os.getenv("SCENEROOM_MODEL", "gemini-flash-latest")

# The single payoff frame. Cut this before cutting anything else.
#
# A Gemini image model rather than imagen-*: the imagen publisher models are not
# available to this project in any region tried, and generate_images is
# deprecated in favour of generate_content anyway. Verified by listing the
# models the project can actually see.
IMAGE_MODEL = os.getenv("SCENEROOM_IMAGE_MODEL", "gemini-3.1-flash-image")
ENABLE_IMAGE = os.getenv("SCENEROOM_ENABLE_IMAGE", "true").lower() == "true"

# Who a contested claim is routed to. A role reads as a placeholder; a named
# person is the point — the product's claim is "get a consultant", not "file a
# ticket". Configurable because every production has a different desk.
ESCALATION_CONTACT = os.getenv("SCENEROOM_ESCALATION_CONTACT", "Standards desk")
