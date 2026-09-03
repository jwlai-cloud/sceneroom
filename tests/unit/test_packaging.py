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

"""The image must carry everything the app reads at runtime.

A missing COPY does not crash the container — fast_api_app guards the static
mount with `FRONTEND.is_dir()`, so the service starts healthy and serves 404
at `/`. That silent failure cost a deploy once; this catches it in CI instead.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

# Directories the app reads at runtime, so they must exist inside the image.
RUNTIME_DIRS = ("app", "frontend")


def test_dockerfile_copies_every_runtime_dir() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    copied = {
        line.split()[1].lstrip("./").rstrip("/")
        for line in dockerfile.splitlines()
        if line.startswith("COPY ") and len(line.split()) >= 3
    }
    missing = [d for d in RUNTIME_DIRS if d not in copied]
    assert not missing, f"Dockerfile never copies {missing} — the image ships without it"


def test_runtime_dirs_exist_in_repo() -> None:
    for d in RUNTIME_DIRS:
        assert (ROOT / d).is_dir(), f"{d}/ is missing from the repo"
