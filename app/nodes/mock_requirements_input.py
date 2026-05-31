from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class MockRequirementsInputNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        raw_requirements = state.get("inputs", {}).get(
            "requirements_text",
            self.config.config.get("default_requirements", ""),
        )
        if not isinstance(raw_requirements, str):
            raise ValueError("mock_requirements_input expected 'requirements_text' to be a string.")
        return {"raw_requirements": raw_requirements}
