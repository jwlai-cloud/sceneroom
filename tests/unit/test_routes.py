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

"""Route resolution, because a shadowed route fails as a plausible 404.

/api/scenes/stream was captured by /api/scenes/{scene_id} and returned
"No such scene." — a real bug that looked like a missing record.
"""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.fast_api_app import app

STREAM_ROUTES = ("/api/stream/scene", "/api/stream/scenes/{scene_id}/decide")


def _get_routes() -> list[APIRoute]:
    return [
        r for r in app.routes if isinstance(r, APIRoute) and "GET" in (r.methods or set())
    ]


def test_stream_routes_exist() -> None:
    paths = {r.path for r in _get_routes()}
    for path in STREAM_ROUTES:
        assert path in paths, f"{path} is not registered"


def test_no_wildcard_shadows_a_stream_route() -> None:
    """No earlier single-segment wildcard may swallow a stream path."""
    routes = _get_routes()
    for path in STREAM_ROUTES:
        target = next(i for i, r in enumerate(routes) if r.path == path)
        segments = path.strip("/").split("/")
        for earlier in routes[:target]:
            other = earlier.path.strip("/").split("/")
            if len(other) != len(segments):
                continue
            shadows = all(
                o.startswith("{") or o == s for o, s in zip(other, segments, strict=True)
            )
            assert not shadows, f"{earlier.path} is declared before {path} and shadows it"
