from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class TestRunnerNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        tests = state.get("node_outputs", {}).get("test_writer", {}).get("generated_tests", [])
        return {
            "run_results": {
                "status": "mock_passed",
                "total": len(tests),
                "passed": len(tests),
                "failed": 0,
            }
        }
