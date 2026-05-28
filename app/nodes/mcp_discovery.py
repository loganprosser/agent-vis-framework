from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class McpDiscoveryNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        discovered = {}
        for tool_id, tool in self.tools.items():
            result = await tool.run(action="list_tools")
            discovered[tool_id] = {
                "ok": result.ok,
                "tools": result.data.get("tools", []) if isinstance(result.data, dict) else [],
                "error": result.error,
            }
        return {"mcp_tools": discovered}
