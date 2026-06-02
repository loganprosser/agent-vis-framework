from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.core.config_loader import ConfigLoader
from app.core.run_store import RunStore


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router(ConfigLoader(), RunStore()))
    return TestClient(app)


def test_workflow_library_only_lists_visible_workflows() -> None:
    client = build_client()

    assert client.get("/workflows").json() == {"workflows": ["ollama_iterative_code_review"]}
    assert client.get("/workflows/starter_three_node").status_code == 200


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
        "has_internal_trace": True,
        "artifact_names": [
            "burr_final_state.json",
            "burr_node_metadata.json",
            "burr_trace.json",
        ],
    }


def test_catalog_exposes_node_types_for_visual_editor_palette() -> None:
    response = build_client().get("/catalog")

    assert response.status_code == 200
    assert "doc_reader" in response.json()["node_types"]
    assert "burr_subsystem" in response.json()["node_types"]


def test_validate_workflow_accepts_nested_burr_action_prompt_files() -> None:
    client = build_client()
    workflow = client.get("/workflows/branching_burr_requirements").json()
    subsystem = next(node for node in workflow["nodes"] if node["type"] == "burr_subsystem")
    topology = subsystem["config"]["topology"]
    topology["actions"][0]["prompt_file"] = (
        "workflows/branching_burr_requirements/subsystems/"
        "validate_and_structure_requirements/actions/validate_requirements.md"
    )
    for node in workflow["nodes"]:
        node.pop("subsystem", None)
        node.pop("subsystem_metadata", None)
        node.pop("_resolved", None)

    response = client.post("/workflows/validate", json=workflow)

    assert response.status_code == 200
    assert response.json()["workflow"]["nodes"][1]["config"]["topology"]["actions"][0][
        "prompt_file"
    ].endswith("actions/validate_requirements.md")


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
    assert metadata["has_internal_trace"] is True
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


def test_run_events_endpoint_exposes_parent_node_lifecycle() -> None:
    client = build_client()

    run = client.post(
        "/workflows/starter_three_node/run",
        json={"inputs": {"requirements_doc": "requirements.md"}},
    ).json()
    response = client.get(f"/runs/{run['run_id']}/events")

    assert response.status_code == 200
    events = response.json()
    assert [event["event_type"] for event in events] == [
        "node_started",
        "node_completed",
        "node_started",
        "node_completed",
        "node_started",
        "node_completed",
    ]
    assert [event["node_id"] for event in events] == [
        "doc_reader",
        "doc_reader",
        "variable_extractor",
        "variable_extractor",
        "report_generator",
        "report_generator",
    ]
    assert events[1]["payload"]["artifact_names"] == ["documents"]
    assert [event["timestamp"] for event in events] == sorted(
        event["timestamp"] for event in events
    )


def test_run_events_endpoint_exposes_burr_subsystem_and_internal_action_path() -> None:
    client = build_client()

    run = client.post(
        "/workflows/branching_burr_requirements/run",
        json={"inputs": {"requirements_text": "short"}},
    ).json()
    events = client.get(f"/runs/{run['run_id']}/events").json()

    subsystem_events = [
        event["event_type"]
        for event in events
        if event["node_id"] == "validate_and_structure_requirements"
    ]
    assert "burr_subsystem_started" in subsystem_events
    assert "burr_subsystem_completed" in subsystem_events
    assert [
        event["payload"]["action"]
        for event in events
        if event["event_type"] == "burr_action_completed"
    ] == [
        "validate_requirements",
        "repair_requirements",
        "structure_requirements",
    ]


def test_run_events_endpoint_exposes_mcp_tool_calls() -> None:
    client = build_client()

    run = client.post("/workflows/mcp_discovery_demo/run", json={"inputs": {}}).json()
    events = client.get(f"/runs/{run['run_id']}/events").json()

    assert [
        (event["event_type"], event["payload"].get("operation"))
        for event in events
        if event["event_type"].startswith("tool_")
    ] == [
        ("tool_started", "list_tools"),
        ("tool_completed", "list_tools"),
    ]
