from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class SolutionPresenterNode(BaseNode):
    """Format the iterative solver output into a polished final report.

    input_keys:  [iterative_solve]
    output_keys: [final_report, solution, quality_score, iterations, accepted]

    The key 'final_report' is picked up by BaseNode._merge_success and set on
    state['final_report'] automatically.
    """

    async def run(self, state: WorkflowState) -> dict:
        solver = state.get("node_outputs", {}).get("iterative_solve", {})
        final_solution = solver.get("final_solution", "")
        final_score = solver.get("final_score", 0)
        iterations = solver.get("iterations_used", 0)
        accepted = solver.get("accepted", False)

        status_note = (
            f"accepted after {iterations} iteration(s) with quality score {final_score}/10"
            if accepted
            else f"reached iteration limit after {iterations} attempt(s) (score: {final_score}/10)"
        )

        report = await self.ask_model(
            state,
            (
                f"Solution status: {status_note}.\n\n"
                f"Final solution:\n{final_solution}\n\n"
                "Present this solution clearly: one-paragraph summary, the code block, "
                "and any notable design decisions."
            ),
        )

        return {
            "final_report": report,
            "solution": final_solution,
            "quality_score": final_score,
            "iterations": iterations,
            "accepted": accepted,
        }
