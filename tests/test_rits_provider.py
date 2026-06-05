from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from app.configure_model import build_parser
from app.core.model_config import upsert_model_provider
from app.core.registry import ModelRegistry
from app.models.base import ModelRequest
from app.models.openai_provider import OpenAIModelProvider
from app.models.rits_provider import RitsModelProvider
from app.schemas.workflow import ModelProviderConfig


def _fake_chat_completion(text: str = "ok") -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = text
    completion.choices[0].finish_reason = "stop"
    completion.model = "test-model"
    completion.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
    return completion


@pytest.mark.asyncio
async def test_rits_provider_injects_rits_api_key_header(monkeypatch) -> None:
    monkeypatch.setenv("RITS_API_KEY", "test-rits-token-123")

    provider = RitsModelProvider(
        "rits_default",
        "GLM-5.1-FP8",
        {"base_url": "http://litellm.test/v1"},
    )

    captured_kwargs: dict = {}

    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        side_effect=lambda **kwargs: (captured_kwargs.update(kwargs) or _fake_chat_completion())
    )
    provider._client = fake_client

    response = await provider.generate(
        ModelRequest(model="GLM-5.1-FP8", system_prompt="hi", messages=[{"role": "user", "content": "yo"}])
    )

    assert response.text == "ok"
    assert captured_kwargs.get("extra_headers") == {"RITS_API_KEY": "test-rits-token-123"}
    assert captured_kwargs["messages"][0] == {"role": "system", "content": "hi"}


@pytest.mark.asyncio
async def test_openai_provider_does_not_send_extra_headers_by_default() -> None:
    provider = OpenAIModelProvider(
        "litellm_proxy", "gpt-4o-mini", {"base_url": "http://litellm.test/v1"}
    )
    captured_kwargs: dict = {}
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        side_effect=lambda **kwargs: (captured_kwargs.update(kwargs) or _fake_chat_completion())
    )
    provider._client = fake_client

    await provider.generate(ModelRequest(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]))

    assert "extra_headers" not in captured_kwargs


def test_registry_routes_rits_and_ibm_to_rits_provider() -> None:
    registry = ModelRegistry()
    registry.register_provider_config(
        ModelProviderConfig.model_validate(
            {"id": "rits_a", "type": "rits", "default_model": "GLM-5.1-FP8", "config": {}}
        )
    )
    registry.register_provider_config(
        ModelProviderConfig.model_validate(
            {"id": "rits_b", "type": "ibm", "default_model": "GLM-5.1-FP8", "config": {}}
        )
    )
    registry.register_provider_config(
        ModelProviderConfig.model_validate(
            {"id": "litellm_c", "type": "litellm", "default_model": "gpt-4o", "config": {}}
        )
    )

    assert isinstance(registry.get("rits_a"), RitsModelProvider)
    assert isinstance(registry.get("rits_b"), RitsModelProvider)
    assert isinstance(registry.get("litellm_c"), OpenAIModelProvider)
    assert not isinstance(registry.get("litellm_c"), RitsModelProvider)


def test_configure_model_persists_rits_provider(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    parser = build_parser()
    args = parser.parse_args(
        [
            "rits",
            "--config-dir",
            str(config_dir),
            "--provider-id",
            "rits_demo",
            "--model",
            "GLM-5.1-FP8",
            "--base-url",
            "http://127.0.0.1:4000/v1",
        ]
    )
    # build_parser sets defaults that match the CLI; emulate main() inline:
    assert args.command == "rits"
    upsert_model_provider(
        config_dir,
        provider_id=args.provider_id,
        provider_type="rits",
        default_model=args.model,
        config={
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "rits_header_env": args.rits_header_env,
            "temperature": args.temperature,
        },
    )

    saved = yaml.safe_load((config_dir / "models.yaml").read_text())
    providers = {p["id"]: p for p in saved["providers"]}
    assert providers["rits_demo"]["type"] == "rits"
    assert providers["rits_demo"]["default_model"] == "GLM-5.1-FP8"
    assert providers["rits_demo"]["config"]["rits_header_env"] == "RITS_API_KEY"
