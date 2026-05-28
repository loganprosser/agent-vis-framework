from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class TestWriterNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        reduced_set = state.get("node_outputs", {}).get("tnt_cli_reducer", {}).get("reduced_test_set", [])
        tests = [
            {
                "name": f"test_checkout_combination_{index + 1}",
                "case": test_case,
                "body": f"assert checkout_flow({test_case!r}).ok",
            }
            for index, test_case in enumerate(reduced_set)
        ]
        return {"generated_tests": tests}
