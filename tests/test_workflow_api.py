from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.core.config_loader import ConfigLoader
from app.core.run_store import RunStore


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router(ConfigLoader(), RunStore()))
    return TestClient(app)


def test_workflow_export_marks_burr_nodes_as_subsystems() -> None:
    response = build_client().get("/workflows/mixed_burr_requirements")

    assert response.status_code == 200
    nodes = {node["id"]: node for node in response.json()["nodes"]}
    assert "subsystem" not in nodes["requirements_input"]
    assert "subsystem_metadata" not in nodes["requirements_input"]
    assert nodes["refine_requirements"]["subsystem"] is True
    assert nodes["refine_requirements"]["subsystem_metadata"] == {
        "runtime": "burr",
        "app_module": "app.subsystems.requirements_burr_app",
        "app_factory": "build_requirements_app",
        "has_internal_trace": False,
        "artifact_names": [
            "burr_final_state.json",
            "burr_node_metadata.json",
            "burr_trace.json",
        ],
    }
