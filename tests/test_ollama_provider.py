import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from app.core.model_config import upsert_model_provider
from app.core.registry import ModelRegistry
from app.models.base import ModelRequest
from app.models.ollama_provider import OllamaModelProvider
from app.schemas.workflow import ModelProviderConfig


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.asyncio
async def test_ollama_provider_translates_neutral_request_to_native_chat_api() -> None:
    provider = OllamaModelProvider(
        "ollama_local",
        "qwen2.5-coder:7b",
        {"base_url": "http://ollama.test", "context_length": 8192, "temperature": 0.2},
    )
    fake_response = FakeResponse(
        {
            "model": "qwen2.5-coder:7b",
            "message": {"role": "assistant", "content": "Local answer"},
            "done": True,
            "prompt_eval_count": 12,
            "eval_count": 4,
        }
    )

    with patch("app.models.ollama_provider.urlopen", return_value=fake_response) as urlopen:
        response = await provider.generate(
            ModelRequest(
                model="qwen2.5-coder:7b",
                system_prompt="Be concise.",
                messages=[{"role": "user", "content": "Hello"}],
            )
        )

    request = urlopen.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://ollama.test/api/chat"
    assert payload["messages"] == [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "Hello"},
    ]
    assert payload["options"] == {"temperature": 0.2, "num_ctx": 8192}
    assert response.text == "Local answer"
    assert response.raw["provider"] == "ollama_local"
    assert response.raw["eval_count"] == 4


def test_model_registry_builds_native_ollama_adapter() -> None:
    registry = ModelRegistry()
    registry.register_provider_config(
        ModelProviderConfig(
            id="ollama_local",
            type="ollama",
            default_model="qwen2.5-coder:7b",
            config={"context_length": 4096},
        )
    )

    assert isinstance(registry.get("ollama_local"), OllamaModelProvider)


def test_upsert_model_provider_preserves_other_providers(tmp_path: Path) -> None:
    models_path = tmp_path / "models.yaml"
    models_path.write_text(
        "providers:\n"
        "  - id: mock\n"
        "    type: mock\n"
        "    default_model: mock-deterministic\n",
        encoding="utf-8",
    )

    upsert_model_provider(
        tmp_path,
        provider_id="ollama_local",
        provider_type="ollama",
        default_model="qwen2.5-coder:7b",
        config={"base_url": "http://127.0.0.1:11434", "context_length": 16384},
    )

    saved = yaml.safe_load(models_path.read_text(encoding="utf-8"))
    assert [provider["id"] for provider in saved["providers"]] == ["mock", "ollama_local"]
    assert saved["providers"][1]["config"]["context_length"] == 16384
