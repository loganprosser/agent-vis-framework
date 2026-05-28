from __future__ import annotations

from typing import Any

from app.tools.base import Tool, ToolResult


class McpTool(Tool):
    async def run(self, **kwargs: Any) -> ToolResult:
        # TODO: Connect real MCP clients/servers here. Nodes should call this
        # abstraction rather than importing MCP-specific code directly.
        return ToolResult(
            data={"request": kwargs, "message": "mock MCP response"},
            logs=[f"McpTool {self.tool_id} returned a mocked response."],
        )
