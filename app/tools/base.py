from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from app.core.runtime_events import RuntimeEventStore, get_runtime_event_context, safe_append_event


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


class ObservableTool(Tool):
    """Decorate an existing tool with run-scoped events without changing its contract."""

    def __init__(self, tool: Tool, *, node_id: str, event_store: RuntimeEventStore) -> None:
        super().__init__(tool.tool_id, tool.config)
        self._tool = tool
        self._node_id = node_id
        self._event_store = event_store

    def __getattr__(self, name: str) -> Any:
        return getattr(self._tool, name)

    async def run(self, **kwargs: Any) -> ToolResult:
        context = get_runtime_event_context()
        run_id = context.run_id if context else None
        payload = self._payload(kwargs, status="running")
        safe_append_event(
            self._event_store,
            run_id,
            "tool_started",
            node_id=self._node_id,
            payload=payload,
        )
        try:
            result = await self._tool.run(**kwargs)
        except Exception as exc:
            safe_append_event(
                self._event_store,
                run_id,
                "tool_failed",
                node_id=self._node_id,
                payload={**payload, "status": "failed", "error": str(exc)},
            )
            raise

        event_type = "tool_completed" if result.ok else "tool_failed"
        safe_append_event(
            self._event_store,
            run_id,
            event_type,
            node_id=self._node_id,
            payload={
                **payload,
                "status": "completed" if result.ok else "failed",
                **({"error": result.error} if result.error else {}),
            },
        )
        return result

    def _payload(self, kwargs: dict[str, Any], *, status: str) -> dict[str, Any]:
        return {
            "node_id": self._node_id,
            "tool_id": self.tool_id,
            "tool_type": type(self._tool).__name__,
            "status": status,
            **({"operation": str(kwargs["action"])} if kwargs.get("action") else {}),
            **({"mcp_tool_name": str(kwargs["name"])} if kwargs.get("name") else {}),
        }
