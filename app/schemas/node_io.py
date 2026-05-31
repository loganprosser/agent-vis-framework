from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.state import WorkflowState


class NodeContext(BaseModel):
    """Typed input passed through the pluggable node execution boundary."""

    node_id: str
    state: WorkflowState
    values: dict[str, Any] = Field(default_factory=dict)


class NodeResult(BaseModel):
    """Normalized result returned by a node implementation."""

    values: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    artifact: Any | None = None
    subsystem_metadata: dict[str, Any] | None = None


class NodeInput(BaseModel):
    node_id: str
    values: dict[str, Any] = Field(default_factory=dict)


class NodeOutput(BaseModel):
    node_id: str
    values: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
