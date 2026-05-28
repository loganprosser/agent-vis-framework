from __future__ import annotations

from datetime import UTC, datetime
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
