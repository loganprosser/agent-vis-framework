from __future__ import annotations

from typing import Any

from app.schemas.workflow import McpServerConfig
from app.tools.base import Tool, ToolResult
from app.tools.mcp_client import StdioMcpClient


class McpTool(Tool):
    def __init__(
        self,
        tool_id: str,
        config: dict[str, Any] | None = None,
        server: McpServerConfig | None = None,
    ) -> None:
        super().__init__(tool_id, config)
        self.server = server

    async def run(self, **kwargs: Any) -> ToolResult:
        if self.server is None:
            return ToolResult(ok=False, error=f"MCP tool {self.tool_id} has no server configured.")
        client = StdioMcpClient(self.server)
        action = kwargs.get("action", "list_tools")
        try:
            if action == "list_tools":
                data = await client.list_tools()
            elif action == "call_tool":
                data = await client.call_tool(str(kwargs["name"]), kwargs.get("arguments") or {})
            else:
                return ToolResult(ok=False, error=f"Unsupported MCP action: {action}")
        except Exception as exc:  # noqa: BLE001 - normalize MCP failures.
            return ToolResult(ok=False, error=str(exc))
        return ToolResult(data=data, logs=[f"McpTool {self.tool_id} completed {action}."])
