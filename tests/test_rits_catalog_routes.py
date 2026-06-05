from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.core.config_loader import ConfigLoader


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    config_dir = tmp_path / "configs"
    (config_dir / "workflows").mkdir(parents=True)
    (config_dir / "models.yaml").write_text("providers: []\n")
    (config_dir / "tools.yaml").write_text("tools: []\n")
    (config_dir / "mcps.yaml").write_text("servers: []\n")

    app = FastAPI()
    app.include_router(create_router(config_loader=ConfigLoader(config_dir=config_dir)))
    return TestClient(app)


def test_rits_models_returns_available_false_when_catalog_missing(client: TestClient) -> None:
    resp = client.get("/providers/rits/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"models": [], "available": False}


def test_rits_models_returns_catalog_when_present(client: TestClient, tmp_path: Path) -> None:
    catalog_dir = tmp_path / "configs" / "providers" / "rits"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "rits-models.json").write_text(
        json.dumps([{"model_name": "GLM-5.1-FP8"}, {"model_name": "Llama-3"}])
    )
    resp = client.get("/providers/rits/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert [m["model_name"] for m in body["models"]] == ["GLM-5.1-FP8", "Llama-3"]
