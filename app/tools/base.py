from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    ok: bool = True
    data: Any = None
    logs: list[str] = Field(default_factory=list)
    error: str | None = None


class Tool(ABC):
    def __init__(self, tool_id: str, config: dict[str, Any] | None = None) -> None:
        self.tool_id = tool_id
        self.config = config or {}

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Run a tool behind a stable interface."""
