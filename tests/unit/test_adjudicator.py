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

"""The escalation rule.

This is the product's one hard guarantee — contested history always reaches a
human — so it is a pure function rather than a prompt, and it is tested.
"""

from __future__ import annotations

from app.agents.adjudicator import escalation_queue, route
from app.models import Claim, ClaimKind, Disposition, Mode, Verdict


def claim(verdict: Verdict, disposition: Disposition = Disposition.PENDING) -> Claim:
    return Claim(
        id="cl-1", kind=ClaimKind.HISTORICAL, text="a claim",
        verdict=verdict, disposition=disposition,
    )


def test_contested_always_reaches_a_human() -> None:
    for mode in (Mode.FICTION, Mode.DOCUMENTARY):
        needs_human, reason = route(claim(Verdict.CONTESTED), mode)
        assert needs_human, f"contested must escalate in {mode}"
        assert "adjudicate" in reason or "disagree" in reason


def test_contradicted_always_reaches_a_human() -> None:
    for mode in (Mode.FICTION, Mode.DOCUMENTARY):
        assert route(claim(Verdict.CONTRADICTED), mode)[0]


def test_unverifiable_depends_on_production_mode() -> None:
    # Same engine, different threshold (PRD §2).
    assert route(claim(Verdict.UNVERIFIABLE), Mode.DOCUMENTARY)[0] is True
    assert route(claim(Verdict.UNVERIFIABLE), Mode.FICTION)[0] is False


def test_verified_needs_nobody() -> None:
    assert route(claim(Verdict.VERIFIED), Mode.DOCUMENTARY)[0] is False


def test_a_decided_claim_leaves_the_queue() -> None:
    decided = claim(Verdict.CONTESTED, Disposition.ESCALATED)
    assert escalation_queue([decided], Mode.FICTION) == []
    assert len(escalation_queue([claim(Verdict.CONTESTED)], Mode.FICTION)) == 1


def test_every_route_gives_a_reason() -> None:
    """The reason is shown to a person, so it must never be blank."""
    for verdict in Verdict:
        for mode in (Mode.FICTION, Mode.DOCUMENTARY):
            assert route(claim(verdict), mode)[1].strip()


def test_unestablished_rights_reach_a_person_in_every_mode() -> None:
    # A rights check that finds nothing writes "refer to the clearance desk".
    # Before this, fiction mode routed it to nobody, so the exposure shipped
    # with no decision attached to it.
    rights = Claim(
        id="cl-r", kind=ClaimKind.RIGHTS, text="a 1963 song plays over the scene",
        verdict=Verdict.UNVERIFIABLE, disposition=Disposition.PENDING,
    )
    for mode in (Mode.FICTION, Mode.DOCUMENTARY):
        needs_human, reason = route(rights, mode)
        assert needs_human, f"unestablished rights must escalate in {mode}"
        assert "clearance" in reason.lower()
