from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models.base import ModelProvider, ModelRequest, ModelResponse


class OllamaModelProvider(ModelProvider):
    """Native Ollama adapter behind the provider-neutral model interface.

    Config keys:
        base_url: Ollama server URL. Defaults to OLLAMA_BASE_URL or
                  http://127.0.0.1:11434.
        context_length: Context window passed to Ollama as num_ctx.
        temperature: Sampling temperature. Defaults to 0.
        timeout_seconds: HTTP timeout. Defaults to 120.
    """

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await asyncio.to_thread(self._generate_sync, request)

    def _generate_sync(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self.default_model
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)

        options: dict[str, Any] = {"temperature": self.config.get("temperature", 0)}
        if self.config.get("context_length") is not None:
            options["num_ctx"] = int(self.config["context_length"])

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        base_url = str(
            self.config.get("base_url")
            or os.environ.get("OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434"
        ).rstrip("/")
        http_request = Request(
            f"{base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(http_request, timeout=float(self.config.get("timeout_seconds", 120))) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return self._error_response(model, f"HTTP {exc.code}: {detail}")
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            return self._error_response(model, str(exc))

        message = body.get("message") or {}
        return ModelResponse(
            text=str(message.get("content") or ""),
            raw={
                "provider": self.provider_id,
                "model": body.get("model", model),
                "done": body.get("done"),
                "done_reason": body.get("done_reason"),
                "prompt_eval_count": body.get("prompt_eval_count"),
                "eval_count": body.get("eval_count"),
                "total_duration": body.get("total_duration"),
            },
        )

    def _error_response(self, model: str, error: str) -> ModelResponse:
        return ModelResponse(
            text=f"[provider error] {error}",
            raw={"provider": self.provider_id, "model": model, "error": error},
        )
