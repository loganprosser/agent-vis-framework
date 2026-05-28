from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NodeInput(BaseModel):
    node_id: str
    values: dict[str, Any] = Field(default_factory=dict)


class NodeOutput(BaseModel):
    node_id: str
    values: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
