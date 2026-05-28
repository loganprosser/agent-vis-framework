from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class VariableClassifierNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        variables = state.get("node_outputs", {}).get("variable_extractor", {}).get("variables", [])
        return {
            "classified_variables": [
                {**variable, "kind": "environment" if variable["name"] in {"browser", "locale"} else "business_rule"}
                for variable in variables
            ]
        }
