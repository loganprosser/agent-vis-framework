from __future__ import annotations

from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class DomainGeneratorNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        return {
            "domains": {
                "browser": ["chrome", "firefox", "safari"],
                "locale": ["en_US", "fr_FR", "ja_JP"],
                "payment_method": ["card", "paypal", "invoice"],
                "shipping_country": ["US", "FR", "JP"],
            }
        }
