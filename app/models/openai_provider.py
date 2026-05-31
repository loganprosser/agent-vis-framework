from __future__ import annotations

import os
from typing import Any

from app.models.base import ModelProvider, ModelRequest, ModelResponse


class OpenAIModelProvider(ModelProvider):
    """OpenAI-compatible provider that works with LiteLLM proxies.

    Config keys:
        base_url: OpenAI-compatible API base URL. Defaults to LITELLM_BASE_URL
                  env var or http://localhost:4002/v1.
        api_key_env: Environment variable name for the API key. Defaults to
                     OPENAI_API_KEY. Falls back to "litellm" if not set.
        temperature: Sampling temperature. Defaults to 0.
    """

    def __init__(self, provider_id: str, default_model: str, config: dict[str, Any] | None = None) -> None:
        super().__init__(provider_id, default_model, config)
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai package is required for OpenAI/LiteLLM providers. "
                "Install with: pip install openai"
            ) from exc

        base_url = self.config.get(
            "base_url",
            os.environ.get("LITELLM_BASE_URL", "http://localhost:4002/v1"),
        )
        api_key_env = self.config.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env, os.environ.get("LITELLM_API_KEY", "litellm"))

        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        return self._client

    async def generate(self, request: ModelRequest) -> ModelResponse:
        client = self._get_client()
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)

        temperature = self.config.get("temperature", 0)

        try:
            response = await client.chat.completions.create(
                model=request.model or self.default_model,
                messages=messages,
                temperature=temperature,
            )
        except Exception as exc:
            return ModelResponse(
                text=f"[provider error] {exc}",
                raw={"provider": self.provider_id, "error": str(exc)},
            )

        text = response.choices[0].message.content if response.choices else ""
        raw = {
            "provider": self.provider_id,
            "model": response.model,
            "usage": {"prompt_tokens": response.usage.prompt_tokens, "completion_tokens": response.usage.completion_tokens} if response.usage else None,
            "finish_reason": response.choices[0].finish_reason if response.choices else None,
        }
        return ModelResponse(text=text or "", raw=raw)
