from __future__ import annotations

from typing import Any

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class TntCliReducerNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        node_outputs = state.get("node_outputs", {})
        variables = node_outputs.get("variable_extractor", {}).get("variables", [])
        domains = node_outputs.get("domain_generator", {}).get("domains", {})
        constraints = node_outputs.get("constraint_builder", {}).get("constraints", [])

        tool = self.tools.get("tnt_cli")
        if tool is not None:
            result = await tool.run(variables=variables, domains=domains, constraints=constraints)
            if not result.ok:
                raise RuntimeError(result.error or "tnt_cli tool failed")
            return result.data

        mcp_tool = self._find_mcp_tool()
        if mcp_tool is not None:
            return await self._run_via_mcp(mcp_tool, variables, domains, constraints)

        return {"reduced_test_set": [], "warning": "tnt_cli tool is not configured for this node."}

    def _find_mcp_tool(self) -> Any | None:
        for tool in self.tools.values():
            if hasattr(tool, "server") and tool.server is not None:
                return tool
        return None

    async def _run_via_mcp(self, mcp_tool: Any, variables: list, domains: dict, constraints: list) -> dict:
        parameters = self._build_testforge_parameters(variables, domains)
        mcp_constraints = self._build_testforge_constraints(constraints)
        arguments: dict[str, Any] = {"parameters": parameters}
        if mcp_constraints:
            arguments["constraints"] = mcp_constraints
        arguments["coverageLevel"] = 2

        result = await mcp_tool.run(action="call_tool", name="generate_test_suite", arguments=arguments)

        if not result.ok:
            error = result.error or "MCP generate_test_suite failed"
            return {"reduced_test_set": [], "error": error, "ok": False}

        data = result.data or {}
        content = data.get("content", []) if isinstance(data, dict) else []
        text = ""
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                break

        if text:
            import json
            try:
                parsed = json.loads(text)
                return {
                    "reduced_test_set": parsed.get("testCases", []),
                    "constraints_applied": constraints,
                    "strategy": f"MCP/TestForge (engine: {parsed.get('engine', 'unknown')})",
                    "ok": True,
                }
            except (json.JSONDecodeError, ValueError):
                return {"reduced_test_set": [], "raw_mcp_response": text, "ok": True}

        return {"reduced_test_set": [], "raw_mcp_response": data, "ok": True}

    @staticmethod
    def _build_testforge_parameters(variables: list, domains: dict) -> list[dict[str, Any]]:
        params: list[dict[str, Any]] = []
        for var in variables:
            name = var.get("name", "") if isinstance(var, dict) else str(var)
            values = domains.get(name, ["unknown"])
            params.append({"name": name, "values": values})
        return params

    @staticmethod
    def _build_testforge_constraints(constraints: list) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for c in constraints:
            if isinstance(c, dict):
                result.append({
                    "type": c.get("type", "exclusion"),
                    "rule": c.get("rule", str(c)),
                })
            else:
                result.append({"type": "exclusion", "rule": str(c)})
        return result
