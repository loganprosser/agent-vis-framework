from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowArtifact(BaseModel):
    """Small wrapper for artifacts that may later be persisted externally."""

    name: str
    kind: str
    data: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
