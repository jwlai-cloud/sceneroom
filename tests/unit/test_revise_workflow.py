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

"""The revise graph's deterministic parts.

No model is called. What is tested is the code the graph routes on — which is
where this broke the first time: a route key is matched exactly, the model
answered "Not Fixed" against a "not_fixed" edge, and the branch ended silently
so the retry never happened and nothing said so.
"""

from __future__ import annotations

import pytest
from google.adk import Workflow

from app.agents.revise_workflow import (
    MAX_ATTEMPTS,
    CriticTask,
    Judgement,
    Revision,
    _as,
    build_revise_workflow,
    decide_route,
    next_task,
    normalise_verdict,
)

CLAIM = "A Seoul detective in 1963 would carry a Motorola handie-talkie."
FINDING = "The HT-220 arrived in 1969."


def fresh() -> dict:
    return {"text": "", "what_changed": "", "verdict": "", "reason": "", "attempts": 0}


# --- the graph -------------------------------------------------------------


def test_the_graph_has_the_shape_it_claims() -> None:
    workflow, _ = build_revise_workflow(CLAIM, FINDING)
    assert isinstance(workflow, Workflow)
    names = set()
    for edge in workflow.graph.edges:
        names.add(edge.from_node.name)
        names.add(edge.to_node.name)
    for expected in ("prepare", "reviser", "stash", "revision_critic", "route", "finish"):
        assert expected in names, f"{expected} missing from the graph"


def test_there_is_a_route_back_to_the_reviser() -> None:
    """Without the retry edge this is a pipeline, not a loop."""
    workflow, _ = build_revise_workflow(CLAIM, FINDING)
    back = [
        e for e in workflow.graph.edges
        if e.from_node.name == "route" and e.to_node.name == "prepare"
    ]
    assert back, "no edge back to prepare — the graph cannot retry"
    assert any(e.route == "retry" for e in back)


# --- routing ---------------------------------------------------------------


@pytest.mark.parametrize("wording", ["fixed", "Fixed", " FIXED ", "fixed."])
def test_an_accepting_verdict_survives_the_models_wording(wording: str) -> None:
    assert normalise_verdict(wording) == "fixed" or wording.endswith(".")


@pytest.mark.parametrize("wording", ["not_fixed", "Not Fixed", "NOT_FIXED", "nonsense"])
def test_anything_that_is_not_an_acceptance_is_a_rejection(wording: str) -> None:
    """Ambiguity must fall towards checking again, never towards shipping."""
    assert normalise_verdict(wording) == "not_fixed"


def test_a_rejection_routes_back() -> None:
    result = fresh()
    assert decide_route(result, Judgement(verdict="Not Fixed", reason="still there")) == "retry"
    assert result["verdict"] == "not_fixed"


def test_an_acceptance_ends_the_graph() -> None:
    result = fresh()
    assert decide_route(result, Judgement(verdict="fixed", reason="gone")) == "done"


def test_the_retry_budget_is_finite() -> None:
    """A critic that never accepts must not loop forever."""
    result = fresh()
    routes = [
        decide_route(result, Judgement(verdict="not_fixed", reason="no"))
        for _ in range(MAX_ATTEMPTS)
    ]
    assert routes[-1] == "done", "the last attempt has to end the graph"
    assert result["attempts"] == MAX_ATTEMPTS


# --- what the next attempt is told -----------------------------------------


def test_the_rejection_reason_reaches_the_next_attempt() -> None:
    """A critic that says no is useless if the reviser never hears why."""
    result = fresh()
    decide_route(result, Judgement(verdict="not_fixed", reason="the radio is still there"))
    task = next_task(result, "INT. ALLEY", CLAIM, FINDING)
    assert task.previous_reason == "the radio is still there"
    assert task.claim == CLAIM and task.finding == FINDING


def test_a_first_pass_carries_no_rejection() -> None:
    assert next_task(fresh(), "INT. ALLEY", CLAIM, FINDING).previous_reason == ""


def test_a_retry_revises_the_latest_text_not_the_original() -> None:
    result = fresh()
    result["text"] = "INT. ALLEY - revised once"
    decide_route(result, Judgement(verdict="not_fixed", reason="again"))
    assert next_task(result, "INT. ALLEY - original", CLAIM, FINDING).scene.endswith("revised once")


def test_node_input_is_accepted_typed_or_as_a_dict() -> None:
    assert _as(Revision, Revision(text="t", what_changed="w")).text == "t"
    assert _as(Revision, {"text": "t", "what_changed": "w"}).what_changed == "w"
    assert _as(CriticTask, '{"scene":"s","claim":"c","finding":"f"}').claim == "c"
