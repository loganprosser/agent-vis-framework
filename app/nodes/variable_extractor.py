from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class VariableExtractorNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        await self.ask_model(state, "Extract combinatorial testing variables.")
        return {
            "variables": [
                {"name": "browser", "source": "requirements", "reason": "UI compatibility"},
                {"name": "locale", "source": "requirements", "reason": "Regional formatting"},
                {"name": "payment_method", "source": "source", "reason": "Payment branching"},
                {"name": "shipping_country", "source": "source", "reason": "Tax and shipping rules"},
            ]
        }
