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

"""The ledger's read-through, which is what makes decisions survive Cloud Run.

Requests are routed independently across instances, so the instance that
receives a decision is often not the one that drafted the scene. Serving that
from memory alone returns "No such scene" and the writer's decision is lost.

BigQuery is not contacted here: these exercise the cache/fallback logic and the
row mapping, which is where the bug would actually live.
"""

from __future__ import annotations

from app.models import Disposition, RevisionEntry, Scene, Source
from app.services.ledger import BigQueryLedger, InMemoryLedger


class FakeBigQueryLedger(BigQueryLedger):
    """BigQueryLedger with the client swapped for a list of rows.

    Subclassed rather than mocked so the real read-through path runs — the
    cache check, the fallback, and the row mapping are the code under test.
    """

    def __init__(self, rows: dict[str, list[dict]]) -> None:
        InMemoryLedger.__init__(self)  # skip the BigQuery client construction
        self._rows = rows
        self._table = "p.d.claims_ledger"
        self._scenes_table = "p.d.scenes"
        self.writes: list[tuple[str, dict]] = []

    def _insert(self, table: str, row: dict) -> None:
        self.writes.append((table, row))

    def _query(self, sql: str, **params) -> list:
        key = "scenes" if "scenes" in sql else "revisions"
        return [r for r in self._rows.get(key, []) if r["scene_id"] == params["scene_id"]]


def a_scene(scene_id: str = "sc-1") -> Scene:
    return Scene(id=scene_id, project="demo", intent="a brief", text="INT. ALLEY")


def test_a_scene_write_also_goes_to_bigquery() -> None:
    ledger = FakeBigQueryLedger({})
    ledger.save_scene(a_scene())
    assert [t for t, _ in ledger.writes] == ["p.d.scenes"]


def test_a_scene_this_instance_never_saw_is_read_back() -> None:
    """The cross-instance case. Without this the decision 404s."""
    ledger = FakeBigQueryLedger(
        {"scenes": [{"scene_id": "sc-1", "payload": a_scene().model_dump_json()}]}
    )
    assert InMemoryLedger.get_scene(ledger, "sc-1") is None  # cold cache
    found = ledger.get_scene("sc-1")
    assert found is not None and found.id == "sc-1"


def test_a_read_back_scene_is_cached_without_being_rewritten() -> None:
    """Warming the cache must not append a new snapshot — that would rewrite
    history on every read of an append-only table."""
    ledger = FakeBigQueryLedger(
        {"scenes": [{"scene_id": "sc-1", "payload": a_scene().model_dump_json()}]}
    )
    ledger.get_scene("sc-1")
    assert ledger.writes == []
    assert InMemoryLedger.get_scene(ledger, "sc-1") is not None


def test_a_missing_scene_is_still_missing() -> None:
    assert FakeBigQueryLedger({}).get_scene("sc-nope") is None


def test_revisions_are_rebuilt_from_rows() -> None:
    ledger = FakeBigQueryLedger(
        {
            "revisions": [
                {
                    "scene_id": "sc-1",
                    "revision": 1,
                    "claim_id": "cl-1",
                    "what_changed": "Kept as deliberate: a claim",
                    "why": "stylised period beat",
                    "disposition": "keep_deliberate",
                    "sources": '[{"title": "t", "url": "https://e.org", "snippet": "s"}]',
                }
            ]
        }
    )
    (entry,) = ledger.revisions("sc-1")
    assert entry.disposition == Disposition.KEEP_DELIBERATE
    assert entry.why == "stylised period beat"
    assert entry.sources[0].url == "https://e.org"


def test_local_revisions_win_over_a_query() -> None:
    """A run in progress must not be overwritten by a stale read."""
    ledger = FakeBigQueryLedger({"revisions": [{"scene_id": "sc-1", "revision": 99}]})
    ledger.append_revision(
        RevisionEntry(revision=1, scene_id="sc-1", what_changed="drafted", why="brief")
    )
    assert [r.revision for r in ledger.revisions("sc-1")] == [1]


def test_an_audit_write_failure_never_breaks_the_request() -> None:
    class DeadClient:
        def insert_rows_json(self, table, rows):
            raise RuntimeError("bigquery is down")

    class Exploding(FakeBigQueryLedger):
        """Fails at the client, so the real _insert guard is what is tested.
        Overriding _insert itself would bypass the protection and pass falsely."""

        def _insert(self, table: str, row: dict) -> None:
            BigQueryLedger._insert(self, table, row)

    ledger = Exploding({})
    ledger._client = DeadClient()
    try:
        ledger.save_scene(a_scene())
    except RuntimeError:
        raise AssertionError("a failed audit write must not surface to the caller") from None
    # ...and the scene is still readable from this instance.
    assert ledger.get_scene("sc-1") is not None


def test_sources_survive_the_json_round_trip() -> None:
    ledger = FakeBigQueryLedger({})
    ledger.append_revision(
        RevisionEntry(
            revision=1,
            scene_id="sc-1",
            what_changed="w",
            why="y",
            sources=[Source(title="t", url="https://e.org", snippet="s")],
        )
    )
    _, row = ledger.writes[0]
    assert "https://e.org" in row["sources"]
