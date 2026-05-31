from __future__ import annotations

from typing import Any

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class McpCallNode(BaseNode):
    """Call a specific MCP tool and store the result in node output.

    Config keys:
        mcp_tool_name: Name of the MCP tool to call (e.g. "calculate_coverage").
        arguments: Dict of arguments to pass to the MCP tool. Can reference
                   prior node outputs via {node_id.key} patterns.
    """

    async def run(self, state: WorkflowState) -> dict[str, Any]:
        mcp_tool_name = self.config.config.get("mcp_tool_name")
        if not mcp_tool_name:
            return {"error": "mcp_call node missing config.mcp_tool_name"}

        static_args = dict(self.config.config.get("arguments", {}))
        arguments = self._resolve_arguments(static_args, state)

        mcp_tool = None
        for tool_id, tool in self.tools.items():
            if hasattr(tool, "server"):
                mcp_tool = tool
                break
        if mcp_tool is None:
            return {"error": "mcp_call node has no MCP tool configured", "mcp_tool_name": mcp_tool_name}

        result = await mcp_tool.run(action="call_tool", name=mcp_tool_name, arguments=arguments)

        if not result.ok:
            return {"error": result.error, "mcp_tool_name": mcp_tool_name, "ok": False}

        data = result.data or {}
        content = data.get("content", []) if isinstance(data, dict) else []
        text_parts = []
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, dict):
                text_parts.append(str(block))

        parsed = None
        if len(text_parts) == 1:
            import json
            try:
                parsed = json.loads(text_parts[0])
            except (json.JSONDecodeError, ValueError):
                parsed = text_parts[0]
        elif text_parts:
            parsed = text_parts

        output: dict[str, Any] = {
            "mcp_tool_name": mcp_tool_name,
            "arguments": arguments,
            "raw": data,
            "ok": True,
        }
        if parsed is not None:
            output["result"] = parsed
        return output

    def _resolve_arguments(self, args: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, value in args.items():
            resolved[key] = self._resolve_value(value, state)
        return resolved

    def _resolve_value(self, value: Any, state: WorkflowState) -> Any:
        if not isinstance(value, str):
            return value
        if not value.startswith("{") or not value.endswith("}"):
            return value

        ref = value[1:-1]
        node_outputs = state.get("node_outputs", {})
        if "." in ref:
            node_id, _, key = ref.partition(".")
            node_data = node_outputs.get(node_id, {})
            if isinstance(node_data, dict):
                result = node_data
                for part in key.split("."):
                    if isinstance(result, dict):
                        result = result.get(part)
                    else:
                        return value
                return result if result is not None else value
        return value
