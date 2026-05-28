from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class TestValidatorNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        tests = state.get("node_outputs", {}).get("test_writer", {}).get("generated_tests", [])
        return {
            "validation_findings": [
                {"severity": "info", "message": f"Validated {len(tests)} generated mocked tests."},
                {"severity": "todo", "message": "Replace placeholder assertions with repository-specific checks."},
            ]
        }
