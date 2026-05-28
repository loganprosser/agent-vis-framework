from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class TntCliReducerNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        node_outputs = state.get("node_outputs", {})
        variables = node_outputs.get("variable_extractor", {}).get("variables", [])
        domains = node_outputs.get("domain_generator", {}).get("domains", {})
        constraints = node_outputs.get("constraint_builder", {}).get("constraints", [])
        tool = self.tools.get("tnt_cli")
        if tool is None:
            return {"reduced_test_set": [], "warning": "tnt_cli tool is not configured for this node."}
        result = await tool.run(variables=variables, domains=domains, constraints=constraints)
        if not result.ok:
            raise RuntimeError(result.error or "tnt_cli tool failed")
        return result.data
