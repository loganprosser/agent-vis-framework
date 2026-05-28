from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class SourceReaderNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        inputs = state.get("inputs", {})
        return {
            "source_files": [
                {
                    "path": inputs.get("source_path", "src/checkout"),
                    "summary": "Mocked source scan found feature flags and checkout branch logic.",
                }
            ]
        }
