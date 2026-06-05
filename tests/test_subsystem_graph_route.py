from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.core.config_loader import ConfigLoader


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    config_dir = tmp_path / "configs"
    workflows = config_dir / "workflows"
    workflows.mkdir(parents=True)
    (config_dir / "models.yaml").write_text("providers: []\n")
    (config_dir / "tools.yaml").write_text("tools: []\n")
    (config_dir / "mcps.yaml").write_text("servers: []\n")

    workflow = {
        "name": "demo",
        "version": "0.1.0",
        "description": "",
        "entrypoint": "sub",
        "nodes": [
            {
                "id": "sub",
                "type": "burr_subsystem",
                "model": "mock-deterministic",
                "provider": "mock",
                "system_prompt": "",
                "input_keys": [],
                "output_keys": [],
                "tools": [],
                "mcps": [],
                "retry_policy": {"max_attempts": 1, "backoff_seconds": 0.0},
                "human_approval": False,
                "config": {
                    "app_module": "app.subsystems.example_burr_app",
                    "app_factory": "build_example_app",
                    "input_map": {"message": "inputs.message"},
                    "output_map": {"greeting": "greeting"},
                    "halt_after": ["greet"],
                },
            },
            {
                "id": "plain",
                "type": "doc_reader",
                "model": "mock-deterministic",
                "provider": "mock",
                "system_prompt": "",
                "input_keys": [],
                "output_keys": [],
                "tools": [],
                "mcps": [],
                "retry_policy": {"max_attempts": 1, "backoff_seconds": 0.0},
                "human_approval": False,
                "config": {},
            },
        ],
        "edges": [],
    }
    (workflows / "demo.yaml").write_text(yaml.safe_dump(workflow, sort_keys=False))

    app = FastAPI()
    app.include_router(create_router(config_loader=ConfigLoader(config_dir=config_dir)))
    return TestClient(app)


def test_returns_mermaid_and_action_metadata(client: TestClient) -> None:
    resp = client.get("/workflows/demo/subsystems/sub/graph")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entrypoint"] == "greet"
    assert "greet" in body["actions"]
    assert body["mermaid"].startswith("graph TD")
    assert body["node_id_map"]["greet"].startswith("n_greet")


def test_404_for_unknown_node(client: TestClient) -> None:
    resp = client.get("/workflows/demo/subsystems/nope/graph")
    assert resp.status_code == 404


def test_400_when_node_is_not_a_burr_subsystem(client: TestClient) -> None:
    resp = client.get("/workflows/demo/subsystems/plain/graph")
    assert resp.status_code == 400
    assert "not a burr_subsystem" in resp.text


def test_404_for_unknown_workflow(client: TestClient) -> None:
    resp = client.get("/workflows/does-not-exist/subsystems/sub/graph")
    assert resp.status_code == 404
