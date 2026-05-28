from __future__ import annotations

from app.models.base import ModelProvider, ModelRequest, ModelResponse


class AnthropicModelProvider(ModelProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        # TODO: Connect Anthropic SDK calls here without leaking provider details
        # into workflow nodes.
        return ModelResponse(
            text=f"[anthropic placeholder] model={request.model or self.default_model}",
            raw={"provider": self.provider_id, "placeholder": True},
        )
