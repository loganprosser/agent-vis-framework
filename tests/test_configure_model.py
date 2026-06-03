"""Tests for app.configure_model CLI and app.core.model_config upsert."""

import subprocess
import sys
from pathlib import Path

import yaml
import pytest

from app.core.model_config import upsert_model_provider


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return tmp_path / "configs"


class TestUpsertModelProvider:
    def test_creates_litellm_provider_in_new_file(self, config_dir: Path) -> None:
        provider = upsert_model_provider(
            config_dir,
            provider_id="litellm",
            provider_type="litellm",
            default_model="gpt-4.1-mini",
            config={
                "base_url": "http://localhost:4002/v1",
                "api_key_env": "LITELLM_API_KEY",
                "temperature": 0,
            },
        )
        assert provider.id == "litellm"
        assert provider.type == "litellm"
        assert provider.default_model == "gpt-4.1-mini"

        raw = yaml.safe_load((config_dir / "models.yaml").read_text())
        assert len(raw["providers"]) == 1
        assert raw["providers"][0]["id"] == "litellm"

    def test_upsert_replaces_existing_provider(self, config_dir: Path) -> None:
        upsert_model_provider(
            config_dir,
            provider_id="litellm",
            provider_type="litellm",
            default_model="old-model",
            config={"base_url": "http://localhost:4002/v1", "api_key_env": "LITELLM_API_KEY"},
        )
        upsert_model_provider(
            config_dir,
            provider_id="litellm",
            provider_type="litellm",
            default_model="new-model",
            config={"base_url": "http://proxy:4002/v1", "api_key_env": "MY_KEY"},
        )

        raw = yaml.safe_load((config_dir / "models.yaml").read_text())
        assert len(raw["providers"]) == 1
        assert raw["providers"][0]["default_model"] == "new-model"
        assert raw["providers"][0]["config"]["base_url"] == "http://proxy:4002/v1"

    def test_preserves_other_providers(self, config_dir: Path) -> None:
        upsert_model_provider(
            config_dir,
            provider_id="mock",
            provider_type="mock",
            default_model="mock-deterministic",
            config={"temperature": 0},
        )
        upsert_model_provider(
            config_dir,
            provider_id="litellm",
            provider_type="litellm",
            default_model="gpt-4.1-mini",
            config={"base_url": "http://localhost:4002/v1", "api_key_env": "LITELLM_API_KEY"},
        )

        raw = yaml.safe_load((config_dir / "models.yaml").read_text())
        ids = [p["id"] for p in raw["providers"]]
        assert "mock" in ids
        assert "litellm" in ids

    def test_litellm_provider_loads_into_registry(self, config_dir: Path) -> None:
        from app.core.config_loader import ConfigLoader
        from app.core.registry import ModelRegistry
        from app.models.openai_provider import OpenAIModelProvider

        upsert_model_provider(
            config_dir,
            provider_id="litellm",
            provider_type="litellm",
            default_model="gpt-4.1-mini",
            config={"base_url": "http://localhost:4002/v1", "api_key_env": "LITELLM_API_KEY"},
        )

        loader = ConfigLoader(config_dir=str(config_dir))
        registry = ModelRegistry()
        for p in loader.load_models().providers:
            registry.register_provider_config(p)

        provider = registry.get("litellm")
        assert isinstance(provider, OpenAIModelProvider)
        assert provider.provider_id == "litellm"


class TestConfigureModelCLI:
    def test_litellm_subcommand_writes_config(self, config_dir: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.configure_model", "litellm",
             "--model", "gpt-4.1-mini",
             "--base-url", "http://localhost:4002/v1",
             "--api-key-env", "LITELLM_API_KEY",
             "--config-dir", str(config_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Saved provider 'litellm'" in result.stdout

        raw = yaml.safe_load((config_dir / "models.yaml").read_text())
        p = raw["providers"][0]
        assert p["id"] == "litellm"
        assert p["type"] == "litellm"
        assert p["default_model"] == "gpt-4.1-mini"
        assert p["config"]["base_url"] == "http://localhost:4002/v1"
        assert p["config"]["api_key_env"] == "LITELLM_API_KEY"

    def test_litellm_subcommand_custom_provider_id(self, config_dir: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.configure_model", "litellm",
             "--model", "claude-3.5-sonnet",
             "--provider-id", "litellm_claude",
             "--base-url", "http://proxy:8080/v1",
             "--config-dir", str(config_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Saved provider 'litellm_claude'" in result.stdout

        raw = yaml.safe_load((config_dir / "models.yaml").read_text())
        assert raw["providers"][0]["id"] == "litellm_claude"

    def test_litellm_empty_model_fails(self, config_dir: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.configure_model", "litellm",
             "--model", "",
             "--config-dir", str(config_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "must not be empty" in result.stderr

    def test_litellm_empty_base_url_fails(self, config_dir: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.configure_model", "litellm",
             "--model", "gpt-4",
             "--base-url", "",
             "--config-dir", str(config_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "must not be empty" in result.stderr

    def test_litellm_empty_api_key_env_fails(self, config_dir: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.configure_model", "litellm",
             "--model", "gpt-4",
             "--api-key-env", "",
             "--config-dir", str(config_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "must not be empty" in result.stderr

    def test_ollama_subcommand_still_works(self, config_dir: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app.configure_model", "ollama",
             "--model", "gemma4:e4b",
             "--context-length", "16384",
             "--config-dir", str(config_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Saved provider 'ollama_local'" in result.stdout

        raw = yaml.safe_load((config_dir / "models.yaml").read_text())
        assert raw["providers"][0]["type"] == "ollama"
