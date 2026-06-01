from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class ProblemAnalyzerNode(BaseNode):
    """Clarify a raw programming problem into a structured spec for downstream agents.

    input_keys:  [problem]
    output_keys: [problem_spec, raw_problem]
    """

    async def run(self, state: WorkflowState) -> dict:
        problem = state.get("inputs", {}).get("problem", "")
        response = await self.ask_model(
            state,
            (
                f"Programming problem:\n\n{problem}\n\n"
                "Identify what must be implemented, expected inputs and outputs, "
                "edge cases, and any constraints. Write a clear implementation spec."
            ),
        )
        return {"problem_spec": response, "raw_problem": problem}
