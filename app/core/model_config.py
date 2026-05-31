from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.schemas.workflow import ModelProviderConfig, ModelsConfig


def upsert_model_provider(
    config_dir: Path | str,
    *,
    provider_id: str,
    provider_type: str,
    default_model: str,
    config: dict[str, Any],
) -> ModelProviderConfig:
    """Add or replace one provider while preserving the provider-neutral config file."""

    path = Path(config_dir) / "models.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    models = ModelsConfig.model_validate(raw or {})
    provider = ModelProviderConfig.model_validate(
        {
            "id": provider_id,
            "type": provider_type,
            "default_model": default_model,
            "config": config,
        }
    )
    providers = [item for item in models.providers if item.id != provider_id]
    providers.append(provider)
    saved = ModelsConfig(providers=providers)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(saved.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return provider
