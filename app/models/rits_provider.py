from __future__ import annotations

from typing import Any

from app.models.openai_provider import OpenAIModelProvider


class RitsModelProvider(OpenAIModelProvider):
    """OpenAI-compatible provider for IBM RITS-hosted models behind a LiteLLM proxy.

    Identical to ``OpenAIModelProvider`` except that the ``RITS_API_KEY`` header
    is injected on every request by default. The header value is read from the
    env var named by ``api_key_env`` (default ``RITS_API_KEY``). Override
    ``extra_headers_env`` in config to point at a different env var.

    Config keys (in addition to ``OpenAIModelProvider``):
        api_key_env: env var holding the OpenAI ``Authorization`` token.
                     Defaults to ``RITS_API_KEY``.
        rits_header_env: env var holding the value of the ``RITS_API_KEY``
                         header sent to the LiteLLM proxy. Defaults to
                         ``RITS_API_KEY``.
    """

    def __init__(self, provider_id: str, default_model: str, config: dict[str, Any] | None = None) -> None:
        merged = dict(config or {})
        merged.setdefault("api_key_env", "RITS_API_KEY")
        rits_env = merged.pop("rits_header_env", "RITS_API_KEY")
        header_map = dict(merged.get("extra_headers_env") or {})
        header_map.setdefault("RITS_API_KEY", rits_env)
        merged["extra_headers_env"] = header_map
        super().__init__(provider_id, default_model, merged)
