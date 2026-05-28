from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class ReportGeneratorNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        outputs = state.get("node_outputs", {})
        report = "\n".join(
            [
                "# Combinatorial Test Generation Report",
                "",
                "## Extracted Variables",
                self._bullet_list(outputs.get("variable_extractor", {}).get("variables", [])),
                "## Generated Domains",
                self._mapping(outputs.get("domain_generator", {}).get("domains", {})),
                "## Constraints",
                self._bullet_list(outputs.get("constraint_builder", {}).get("constraints", [])),
                "## Reduced Test Set",
                self._bullet_list(outputs.get("tnt_cli_reducer", {}).get("reduced_test_set", [])),
                "## Generated Tests",
                self._bullet_list(outputs.get("test_writer", {}).get("generated_tests", [])),
                "## Validation Findings",
                self._bullet_list(outputs.get("test_validator", {}).get("validation_findings", [])),
                "## Run Results",
                self._mapping(outputs.get("test_runner", {}).get("run_results", {})),
            ]
        )
        return {"final_report": report}

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
