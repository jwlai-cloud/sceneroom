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

"""The access gate.

It guards spend, not secrets: every endpoint behind it calls Gemini and
Parallel, and the URL is public for the whole judging window. The failure that
matters is a gate that looks shut and is not, so the list of protected routes is
asserted rather than trusted.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app import fast_api_app as api

# Every route that spends money on a model or a search.
MUST_BE_GATED = {
    ("POST", "/api/scenes"),
    ("POST", "/api/scenes/demo"),
    ("POST", "/api/scenes/{scene_id}/decide"),
    ("GET", "/api/stream/scene"),
    ("GET", "/api/stream/scenes/{scene_id}/decide"),
}


class FakeRequest:
    def __init__(self, cookie: str | None = None) -> None:
        self.cookies = {api.ACCESS_COOKIE: cookie} if cookie is not None else {}


def test_every_spending_route_is_gated() -> None:
    """A new expensive endpoint added without the dependency fails here."""
    gated = set()
    for route in api.app.routes:
        if not isinstance(route, APIRoute):
            continue
        names = {d.call.__name__ for d in route.dependant.dependencies if d.call}
        if "require_access" in names:
            gated |= {(m, route.path) for m in route.methods if m != "HEAD"}
    missing = MUST_BE_GATED - gated
    assert not missing, f"these spend money and are not gated: {sorted(missing)}"


def test_open_when_no_code_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local development and the tests must not need a code."""
    monkeypatch.setattr(api, "ACCESS_CODE", "")
    api.require_access(FakeRequest())  # must not raise


def test_the_wrong_code_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "ACCESS_CODE", "open-sesame")
    for cookie in (None, "", "nearly-open-sesame", "OPEN-SESAME"):
        with pytest.raises(HTTPException) as caught:
            api.require_access(FakeRequest(cookie))
        assert caught.value.status_code == 401


def test_the_right_code_is_admitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "ACCESS_CODE", "open-sesame")
    api.require_access(FakeRequest("open-sesame"))  # must not raise


def test_health_and_reads_stay_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """A judge should see the service is alive without entering anything, and a
    gate that hides /api/health would look like an outage."""
    monkeypatch.setattr(api, "ACCESS_CODE", "open-sesame")
    open_paths = {"/api/health", "/api/access", "/api/scenes/{scene_id}/provenance"}
    for route in api.app.routes:
        if isinstance(route, APIRoute) and route.path in open_paths:
            names = {d.call.__name__ for d in route.dependant.dependencies if d.call}
            assert "require_access" not in names, f"{route.path} should stay readable"


def test_a_key_link_admits_in_one_click() -> None:
    """A submission form has nowhere to put an access code, so the hosted URL
    itself has to work. `?key=` sets the cookie and redirects to a clean `/`."""
    import app.fast_api_app as mod
    from fastapi.testclient import TestClient

    original = mod.ACCESS_CODE
    mod.ACCESS_CODE = "open-sesame"
    try:
        client = TestClient(mod.app, follow_redirects=False)

        ok = client.get("/?key=open-sesame")
        assert ok.status_code == 303
        assert ok.headers["location"] == "/"
        assert mod.ACCESS_COOKIE in ok.cookies

        # A wrong key is not an error; it falls through to the gate.
        bad = client.get("/?key=nope")
        assert bad.status_code == 200
        assert mod.ACCESS_COOKIE not in bad.cookies
    finally:
        mod.ACCESS_CODE = original
