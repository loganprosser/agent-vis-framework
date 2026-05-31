from __future__ import annotations

from app.nodes.base import BaseNode
from app.schemas.node_io import NodeContext, NodeResult


class RequirementsReportNode(BaseNode):
    async def execute(self, context: NodeContext) -> NodeResult:
        structured_requirements = context.values["refine_requirements"]["structured_requirements"]
        summary = (
            "# Requirements Summary\n\n"
            f"- Validated: {structured_requirements['validated']}\n"
            f"- Requirements: {structured_requirements['requirement_count']}\n"
            f"- Summary: {structured_requirements['summary']}"
        )
        return NodeResult(
            values={
                "structured_requirements": structured_requirements,
                "final_report": summary,
            },
            artifact={"type": "requirements_summary", "summary": summary},
        )
