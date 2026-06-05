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
        extra_headers: Static header dict appended to each request.
        extra_headers_env: Mapping of header_name -> env_var. Each env var is
                           read at call time and merged into extra_headers.
                           Useful for RITS where the proxy expects
                           ``RITS_API_KEY: <value>`` alongside the standard
                           OpenAI ``Authorization`` header.
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

    def _resolve_extra_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        static = self.config.get("extra_headers") or {}
        if isinstance(static, dict):
            headers.update({str(k): str(v) for k, v in static.items() if v is not None})
        env_map = self.config.get("extra_headers_env") or {}
        if isinstance(env_map, dict):
            for header_name, env_var in env_map.items():
                value = os.environ.get(str(env_var))
                if value:
                    headers[str(header_name)] = value
        return headers

    async def generate(self, request: ModelRequest) -> ModelResponse:
        client = self._get_client()
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)

        temperature = self.config.get("temperature", 0)
        extra_headers = self._resolve_extra_headers()

        try:
            kwargs: dict[str, Any] = {
                "model": request.model or self.default_model,
                "messages": messages,
                "temperature": temperature,
            }
            if extra_headers:
                kwargs["extra_headers"] = extra_headers
            response = await client.chat.completions.create(**kwargs)
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
