from __future__ import annotations

import json

from app.models.base import ModelProvider, ModelRequest, ModelResponse


class MockModelProvider(ModelProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload = {
            "provider": self.provider_id,
            "model": request.model or self.default_model,
            "summary": "deterministic mock response",
            "context_keys": sorted(request.context.keys()),
        }
        return ModelResponse(text=json.dumps(payload, sort_keys=True), raw=payload)
