from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.state import WorkflowState


class RunRecord(BaseModel):
    run_id: str
    workflow_name: str
    status: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    inputs: dict[str, Any] = Field(default_factory=dict)
    state: WorkflowState | None = None
    error: str | None = None


class RunEvent(BaseModel):
    id: int
    run_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    node_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunStore:
    """In-memory run store with a small API that can later wrap SQL storage."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._events: dict[str, list[RunEvent]] = {}
        self._next_event_id = 1
        self._event_lock = threading.Lock()

    def create(self, workflow_name: str, inputs: dict[str, Any]) -> RunRecord:
        run = RunRecord(
            run_id=str(uuid4()),
            workflow_name=workflow_name,
            status="created",
            inputs=inputs,
        )
        self._runs[run.run_id] = run
        return run

    def mark_running(self, run_id: str) -> RunRecord:
        return self._update(run_id, status="running")

    def mark_completed(self, run_id: str, state: WorkflowState) -> RunRecord:
        return self._update(run_id, status="completed", state=state)

    def mark_failed(self, run_id: str, error: str, state: WorkflowState | None = None) -> RunRecord:
        return self._update(run_id, status="failed", error=error, state=state)

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def append_event(
        self,
        run_id: str,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEvent:
        with self._event_lock:
            event = RunEvent(
                id=self._next_event_id,
                run_id=run_id,
                event_type=event_type,
                node_id=node_id,
                payload=payload or {},
            )
            self._next_event_id += 1
            self._events.setdefault(run_id, []).append(event)
        return event

    def list_events(self, run_id: str) -> list[RunEvent]:
        return sorted(self._events.get(run_id, []), key=lambda event: (event.timestamp, event.id))

    def _update(self, run_id: str, **changes: Any) -> RunRecord:
        run = self._runs[run_id]
        updated = run.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        self._runs[run_id] = updated
        return updated


class SQLiteRunStore(RunStore):
    """SQLite-backed run store with the same small API as the memory store."""

    def __init__(self, db_path: Path | str = ".runs/workflows.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def create(self, workflow_name: str, inputs: dict[str, Any]) -> RunRecord:
        run = RunRecord(run_id=str(uuid4()), workflow_name=workflow_name, status="created", inputs=inputs)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (run_id, workflow_name, status, created_at, updated_at, inputs_json, state_json, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._to_row(run),
            )
        return run

    def get(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._from_row(row) if row else None

    def append_event(
        self,
        run_id: str,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEvent:
        timestamp = datetime.now(UTC)
        event_payload = payload or {}
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO run_events (run_id, timestamp, event_type, node_id, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, timestamp.isoformat(), event_type, node_id, json.dumps(event_payload, default=str)),
            )
        return RunEvent(
            id=cursor.lastrowid,
            run_id=run_id,
            timestamp=timestamp,
            event_type=event_type,
            node_id=node_id,
            payload=event_payload,
        )

    def list_events(self, run_id: str) -> list[RunEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, run_id, timestamp, event_type, node_id, payload_json
                FROM run_events
                WHERE run_id = ?
                ORDER BY timestamp, id
                """,
                (run_id,),
            ).fetchall()
        return [
            RunEvent.model_validate(
                {
                    "id": row["id"],
                    "run_id": row["run_id"],
                    "timestamp": row["timestamp"],
                    "event_type": row["event_type"],
                    "node_id": row["node_id"],
                    "payload": json.loads(row["payload_json"]),
                }
            )
            for row in rows
        ]

    def _update(self, run_id: str, **changes: Any) -> RunRecord:
        run = self.get(run_id)
        if run is None:
            raise KeyError(run_id)
        updated = run.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET workflow_name = ?, status = ?, created_at = ?, updated_at = ?, inputs_json = ?, state_json = ?, error = ?
                WHERE run_id = ?
                """,
                (*self._to_row(updated)[1:], updated.run_id),
            )
        return updated

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    workflow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    inputs_json TEXT NOT NULL,
                    state_json TEXT,
                    error TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    node_id TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_run_events_run_id_timestamp
                ON run_events (run_id, timestamp, id)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _to_row(self, run: RunRecord) -> tuple[Any, ...]:
        payload = run.model_dump(mode="json")
        return (
            run.run_id,
            run.workflow_name,
            run.status,
            payload["created_at"],
            payload["updated_at"],
            json.dumps(payload["inputs"]),
            json.dumps(payload["state"]) if payload["state"] is not None else None,
            run.error,
        )

    def _from_row(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord.model_validate(
            {
                "run_id": row["run_id"],
                "workflow_name": row["workflow_name"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "inputs": json.loads(row["inputs_json"]),
                "state": json.loads(row["state_json"]) if row["state_json"] else None,
                "error": row["error"],
            }
        )


def create_run_store() -> RunStore:
    backend = os.getenv("WORKFLOW_RUN_STORE", "sqlite").lower()
    if backend == "memory":
        return RunStore()
    return SQLiteRunStore(os.getenv("WORKFLOW_RUN_DB", ".runs/workflows.sqlite3"))
