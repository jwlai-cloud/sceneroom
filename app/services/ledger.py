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

"""The claims ledger — the product's system of record.

Append-only provenance: what was checked, against which source, what the human
decided, and why. Two implementations behind one interface:

- `InMemoryLedger` — default, for local dev and the walking skeleton.
- `BigQueryLedger`  — used when `BIGQUERY_DATASET` is set.

Callers never branch on which is active; `get_ledger()` decides once.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Protocol

from app.models import RevisionEntry, Scene

logger = logging.getLogger(__name__)

BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "")
BIGQUERY_TABLE = os.getenv("BIGQUERY_TABLE", "claims_ledger")
BIGQUERY_SCENES_TABLE = os.getenv("BIGQUERY_SCENES_TABLE", "scenes")
BIGQUERY_LOCATION = os.getenv("BIGQUERY_LOCATION", "US")


def _utcnow() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


class Ledger(Protocol):
    def save_scene(self, scene: Scene) -> None: ...
    def get_scene(self, scene_id: str) -> Scene | None: ...
    def list_scenes(self) -> list[Scene]: ...
    def append_revision(self, entry: RevisionEntry) -> None: ...
    def revisions(self, scene_id: str) -> list[RevisionEntry]: ...
    @property
    def backend(self) -> str: ...
    @property
    def target(self) -> str: ...


class InMemoryLedger:
    """Process-local. Fine for a single-instance demo; loses state on restart."""

    def __init__(self) -> None:
        self._scenes: dict[str, Scene] = {}
        self._revisions: list[RevisionEntry] = []

    def save_scene(self, scene: Scene) -> None:
        self._scenes[scene.id] = scene

    def get_scene(self, scene_id: str) -> Scene | None:
        return self._scenes.get(scene_id)

    def list_scenes(self) -> list[Scene]:
        return list(self._scenes.values())

    def append_revision(self, entry: RevisionEntry) -> None:
        self._revisions.append(entry)

    def revisions(self, scene_id: str) -> list[RevisionEntry]:
        return [r for r in self._revisions if r.scene_id == scene_id]

    @property
    def backend(self) -> str:
        return "in-memory"

    @property
    def target(self) -> str:
        return "in-memory — set BIGQUERY_DATASET to persist"


class BigQueryLedger(InMemoryLedger):
    """Durable ledger. Every write streams to BigQuery; memory is a read cache
    in front of it.

    Scenes are persisted too, not just revisions. Cloud Run routes each request
    independently across instances, so a writer who drafts a scene on one
    instance can land their decision on another. With state only in memory that
    request 404s as "No such scene" — a lost decision that looks like a missing
    record. Reads therefore fall back to BigQuery on a cache miss.

    Both tables are append-only, which is the product's whole claim: a
    provenance record you can produce later is worthless if rows can be edited.
    A scene's current state is its most recent snapshot.
    """

    def __init__(self) -> None:
        super().__init__()
        from google.cloud import bigquery  # lazily imported; optional at runtime

        self._client = bigquery.Client(location=BIGQUERY_LOCATION or None)
        base = f"{self._client.project}.{BIGQUERY_DATASET}"
        self._table = f"{base}.{BIGQUERY_TABLE}"
        self._scenes_table = f"{base}.{BIGQUERY_SCENES_TABLE}"
        self._ensure_dataset()
        self._ensure_tables()

    # --- schema ------------------------------------------------------------

    def _ensure_dataset(self) -> None:
        """Create the dataset if we are allowed to, and shrug if we are not.

        In production the runtime account holds dataEditor on this dataset and
        nothing wider, so it cannot create datasets at all — the dataset is
        provisioned once, out of band. Demanding that permission at startup
        would mean granting project-level rights for a call that succeeds once
        and is refused every day after. If the dataset is genuinely absent,
        table creation fails next and says so.
        """
        from google.cloud import bigquery

        ref = bigquery.Dataset(f"{self._client.project}.{BIGQUERY_DATASET}")
        ref.location = BIGQUERY_LOCATION
        try:
            self._client.create_dataset(ref, exists_ok=True)
        except Exception as exc:
            logger.debug("Dataset not created (%s); assuming it already exists", exc)

    def _ensure_tables(self) -> None:
        from google.cloud import bigquery

        revisions = [
            bigquery.SchemaField("scene_id", "STRING"),
            bigquery.SchemaField("revision", "INT64"),
            bigquery.SchemaField("claim_id", "STRING"),
            bigquery.SchemaField("what_changed", "STRING"),
            bigquery.SchemaField("why", "STRING"),
            bigquery.SchemaField("disposition", "STRING"),
            bigquery.SchemaField("sources", "STRING"),  # JSON blob
            bigquery.SchemaField("recorded_at", "TIMESTAMP"),
        ]
        # The scene is stored whole as JSON rather than shredded into columns:
        # the model still moves, and a migration that loses provenance is worse
        # than a column we cannot GROUP BY.
        scenes = [
            bigquery.SchemaField("scene_id", "STRING"),
            bigquery.SchemaField("project", "STRING"),
            bigquery.SchemaField("revision", "INT64"),
            bigquery.SchemaField("payload", "STRING"),
            bigquery.SchemaField("recorded_at", "TIMESTAMP"),
        ]
        for name, schema in ((self._table, revisions), (self._scenes_table, scenes)):
            self._client.create_table(bigquery.Table(name, schema=schema), exists_ok=True)

    # --- writes ------------------------------------------------------------

    def _insert(self, table: str, row: dict) -> None:
        """Never fail the user's request because an audit write failed — log
        loudly instead. The in-memory copy still serves this request."""
        try:
            errors = self._client.insert_rows_json(table, [row])
        except Exception as exc:
            logger.error("BigQuery insert to %s raised: %s", table, exc)
            return
        if errors:
            logger.error("BigQuery insert to %s failed: %s", table, errors)

    def save_scene(self, scene: Scene) -> None:
        super().save_scene(scene)
        self._insert(
            self._scenes_table,
            {
                "scene_id": scene.id,
                "project": scene.project,
                "revision": scene.revision,
                "payload": scene.model_dump_json(),
                "recorded_at": _utcnow(),
            },
        )

    def append_revision(self, entry: RevisionEntry) -> None:
        super().append_revision(entry)
        self._insert(
            self._table,
            {
                "scene_id": entry.scene_id,
                "revision": entry.revision,
                "claim_id": entry.claim_id,
                "what_changed": entry.what_changed,
                "why": entry.why,
                "disposition": entry.disposition.value if entry.disposition else None,
                "sources": json.dumps([s.model_dump() for s in entry.sources]),
                "recorded_at": _utcnow(),
            },
        )

    # --- reads -------------------------------------------------------------

    def _query(self, sql: str, **params) -> list:
        from google.cloud import bigquery

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(k, "STRING", v) for k, v in params.items()
            ]
        )
        try:
            return list(self._client.query(sql, job_config=job_config).result())
        except Exception as exc:
            # A read failure degrades to "not found", never to a 500.
            logger.warning("BigQuery read failed: %s", exc)
            return []

    def get_scene(self, scene_id: str) -> Scene | None:
        cached = super().get_scene(scene_id)
        if cached is not None:
            return cached
        rows = self._query(
            f"SELECT payload FROM `{self._scenes_table}` "
            "WHERE scene_id = @scene_id ORDER BY recorded_at DESC LIMIT 1",
            scene_id=scene_id,
        )
        if not rows:
            return None
        try:
            scene = Scene.model_validate_json(rows[0]["payload"])
        except Exception:  # a snapshot from an older model shape
            # A snapshot written by an older model shape. `list_scenes` already
            # tolerates this; without the same guard here one stale row turns
            # every read of that scene into a 500.
            logger.warning("scene %s has a payload this model cannot read", scene_id)
            return None
        super().save_scene(scene)  # warm the cache; do not re-write to BigQuery
        return scene

    def list_scenes(self) -> list[Scene]:
        """Most recent snapshot per scene, newest first.

        Read from BigQuery rather than memory: the point of the list is the work
        this browser did *not* do on this instance.
        """
        # A window function, not a correlated subquery: an unqualified
        # `scene_id` inside the subquery bound to the subquery's own table, so
        # the predicate was always true and MAX ran over the whole table —
        # which returned exactly one scene, always.
        rows = self._query(
            "SELECT payload FROM ("
            "  SELECT payload, ROW_NUMBER() OVER ("
            "    PARTITION BY scene_id ORDER BY recorded_at DESC) AS rn, recorded_at"
            f"  FROM `{self._scenes_table}`"
            ") WHERE rn = 1 ORDER BY recorded_at DESC LIMIT 50"
        )
        out: list[Scene] = []
        for r in rows:
            try:
                out.append(Scene.model_validate_json(r["payload"]))
            except Exception:  # a snapshot from an older model shape
                continue
        return out or super().list_scenes()

    def revisions(self, scene_id: str) -> list[RevisionEntry]:
        local = super().revisions(scene_id)
        if local:
            return local
        rows = self._query(
            f"SELECT * FROM `{self._table}` "
            "WHERE scene_id = @scene_id ORDER BY recorded_at ASC",
            scene_id=scene_id,
        )
        return [
            RevisionEntry(
                revision=r["revision"],
                scene_id=r["scene_id"],
                claim_id=r["claim_id"] or "",
                what_changed=r["what_changed"] or "",
                why=r["why"] or "",
                disposition=r["disposition"] or None,
                sources=json.loads(r["sources"] or "[]"),
            )
            for r in rows
        ]

    @property
    def backend(self) -> str:
        return "bigquery"

    @property
    def target(self) -> str:
        return f"bigquery://{self._table}"


_ledger: Ledger | None = None


def get_ledger() -> Ledger:
    """Singleton. Falls back to in-memory if BigQuery can't be reached, so a
    misconfigured dataset degrades the audit trail rather than the product."""
    global _ledger
    if _ledger is not None:
        return _ledger

    if BIGQUERY_DATASET:
        try:
            _ledger = BigQueryLedger()
            logger.info("Ledger backend: %s", _ledger.backend)
            return _ledger
        except Exception as exc:
            logger.warning("BigQuery ledger unavailable (%s); using in-memory", exc)

    _ledger = InMemoryLedger()
    return _ledger
