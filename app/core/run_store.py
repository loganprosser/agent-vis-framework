from __future__ import annotations

import json
import os
import sqlite3
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


class RunStore:
    """In-memory run store with a small API that can later wrap SQL storage."""

    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

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
