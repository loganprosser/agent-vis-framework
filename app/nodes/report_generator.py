from __future__ import annotations

from typing import Any

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class ReportGeneratorNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        outputs = state.get("node_outputs", {})
        sections = [
            "# Combinatorial Test Generation Report",
            "",
            self._section_variables(outputs),
            self._section_mcp_discovery(outputs),
            self._section_mcp_results(outputs),
            self._section_domains(outputs),
            self._section_constraints(outputs),
            self._section_reduced_set(outputs),
            self._section_generated_tests(outputs),
            self._section_validation(outputs),
            self._section_run_results(outputs),
        ]
        return {"final_report": "\n".join(sections)}

    def _section_variables(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("variable_extractor", outputs.get("extract_variables", {}))
        variables = data.get("variables", [])
        if not variables:
            return ""
        return "## Extracted Variables\n" + self._bullet_list(variables) + "\n"

    def _section_mcp_discovery(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("discover_mcp_tools", outputs.get("discover_testforge_tools", {}))
        mcp_tools = data.get("mcp_tools", {})
        if not mcp_tools:
            return ""
        lines = ["## Discovered MCP Tools", ""]
        for server_id, info in mcp_tools.items():
            if isinstance(info, dict) and info.get("ok"):
                tool_names = [t["name"] for t in info.get("tools", []) if isinstance(t, dict)]
                lines.append(f"- **{server_id}**: {', '.join(tool_names) or 'none'}")
            elif isinstance(info, dict):
                lines.append(f"- **{server_id}**: error — {info.get('error', 'unknown')}")
        return "\n".join(lines) + "\n"

    def _section_mcp_results(self, outputs: dict[str, Any]) -> str:
        mcp_nodes = [
            (k, v) for k, v in outputs.items()
            if isinstance(v, dict) and v.get("mcp_tool_name")
        ]
        if not mcp_nodes:
            return ""
        lines = ["## MCP Tool Results", ""]
        for node_id, data in mcp_nodes:
            tool_name = data.get("mcp_tool_name", node_id)
            result = data.get("result")
            ok = data.get("ok", True)
            status = "ok" if ok else "error"
            lines.append(f"### {tool_name} ({status})")
            if isinstance(result, dict):
                for key, value in result.items():
                    lines.append(f"- **{key}**: {value}")
            elif result is not None:
                lines.append(f"```")
                lines.append(str(result))
                lines.append(f"```")
            lines.append("")
        return "\n".join(lines)

    def _section_domains(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("domain_generator", {})
        domains = data.get("domains", {})
        if not domains:
            return ""
        return "## Generated Domains\n" + self._mapping(domains) + "\n"

    def _section_constraints(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("constraint_builder", {})
        constraints = data.get("constraints", [])
        if not constraints:
            return ""
        return "## Constraints\n" + self._bullet_list(constraints) + "\n"

    def _section_reduced_set(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("tnt_cli_reducer", {})
        reduced = data.get("reduced_test_set", [])
        if not reduced:
            return ""
        return "## Reduced Test Set\n" + self._bullet_list(reduced) + "\n"

    def _section_generated_tests(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("test_writer", {})
        tests = data.get("generated_tests", [])
        if not tests:
            return ""
        return "## Generated Tests\n" + self._bullet_list(tests) + "\n"

    def _section_validation(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("test_validator", {})
        findings = data.get("validation_findings", [])
        if not findings:
            return ""
        return "## Validation Findings\n" + self._bullet_list(findings) + "\n"

    def _section_run_results(self, outputs: dict[str, Any]) -> str:
        data = outputs.get("test_runner", {})
        results = data.get("run_results", {})
        if not results:
            return ""
        return "## Run Results\n" + self._mapping(results) + "\n"

    def _bullet_list(self, values: list | dict) -> str:
        if not values:
            return "- None\n"
        if isinstance(values, dict):
            values = list(values.items())
        return "\n".join(f"- `{value}`" for value in values) + "\n"

    def _mapping(self, values: dict) -> str:
        if not values:
            return "- None\n"
        return "\n".join(f"- **{key}**: `{value}`" for key, value in values.items()) + "\n"
