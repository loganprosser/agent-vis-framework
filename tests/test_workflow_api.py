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


def test_run_details_expose_burr_subsystem_metadata_and_artifact_links() -> None:
    client = build_client()

    response = client.post(
        "/workflows/branching_burr_requirements/run",
        json={"inputs": {"requirements_text": "short"}},
    )

    assert response.status_code == 200
    run = response.json()
    state = run["state"]
    metadata = state["_subsystems"]["validate_and_structure_requirements"]
    assert metadata["runtime"] == "burr"
    assert metadata["status"] == "completed"
    assert metadata["terminal_state"] == "complete"
    assert metadata["halt_reason"] == "halt_after: structure_requirements"
    assert metadata["app_module"] == "app.subsystems.branching_requirements_burr_app"
    assert metadata["app_factory"] == "build_branching_requirements_app"
    assert metadata["artifact_names"] == [
        "burr_final_state.json",
        "burr_node_metadata.json",
        "burr_trace.json",
    ]
    assert state["logs"][-1] == "validate_and_structure_requirements: completed"

    artifact_response = client.get(
        f"/runs/{run['run_id']}/artifacts/"
        "validate_and_structure_requirements/burr_final_state.json"
    )

    assert artifact_response.status_code == 200
    assert artifact_response.json()["repair_happened"] is True


def test_workflow_export_exposes_editable_burr_topology() -> None:
    response = build_client().get("/workflows/branching_burr_requirements")

    assert response.status_code == 200
    nodes = {node["id"]: node for node in response.json()["nodes"]}
    subsystem = nodes["validate_and_structure_requirements"]
    topology = subsystem["subsystem_metadata"]["topology"]

    assert topology["entrypoint"] == "validate_requirements"
    assert [action["id"] for action in topology["actions"]] == [
        "validate_requirements",
        "repair_requirements",
        "structure_requirements",
    ]
    assert topology["transitions"][0] == {
        "source": "validate_requirements",
        "target": "repair_requirements",
        "condition": "validation_status == repair_required",
    }
