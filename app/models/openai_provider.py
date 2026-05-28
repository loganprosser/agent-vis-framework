from __future__ import annotations

from app.models.base import ModelProvider, ModelRequest, ModelResponse


class OpenAIModelProvider(ModelProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        # TODO: Connect the official OpenAI SDK here. Keep auth, retries, and
        # provider-specific request mapping isolated in this adapter.
        return ModelResponse(
            text=f"[openai placeholder] model={request.model or self.default_model}",
            raw={"provider": self.provider_id, "placeholder": True},
        )
