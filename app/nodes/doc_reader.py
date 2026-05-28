from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class DocReaderNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        inputs = state.get("inputs", {})
        return {
            "documents": [
                {
                    "name": inputs.get("requirements_doc", "mock_requirements.md"),
                    "summary": "Checkout supports browser, locale, payment method, and shipping country variants.",
                }
            ]
        }
