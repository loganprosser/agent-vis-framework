from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class ConstraintBuilderNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        return {
            "constraints": [
                "payment_method=invoice requires shipping_country=US",
                "browser=safari should be paired with locale=en_US or ja_JP",
            ]
        }
