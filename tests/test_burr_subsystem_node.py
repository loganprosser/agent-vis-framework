from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state
from app.models.mock_provider import MockModelProvider
from app.nodes.burr_subsystem import BurrSubsystemNode
from app.schemas.workflow import NodeConfig


def build_node(**config) -> BurrSubsystemNode:
    return BurrSubsystemNode(
        config=NodeConfig(id="burr_test", type="burr_subsystem", config=config),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
    )


def assert_node_error(result, message: str) -> None:
    assert result["errors"] == [{"node_id": "burr_test", "message": message}]


def test_burr_subsystem_config_is_validated_when_workflow_loads(tmp_path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    (workflow_dir / "invalid_burr.yaml").write_text(
        """
name: invalid_burr
entrypoint: burr
nodes:
  - id: burr
    type: burr_subsystem
    config:
      app_module: app.subsystems.example_burr_app
      app_factory: build_example_app
edges: []
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="set exactly one of halt_after or terminal_states"):
        ConfigLoader(tmp_path).load_workflow("invalid_burr")


def test_burr_subsystem_config_defaults_are_applied_when_workflow_loads() -> None:
    workflow = ConfigLoader().load_workflow("burr_subsystem_demo")
    config = workflow.nodes[0].config

    assert config["artifact_name"] == "burr_final_state"
    assert config["fail_on_error"] is True


@pytest.mark.asyncio
async def test_burr_subsystem_runs_from_workflow_yaml() -> None:
    loader = ConfigLoader()
    workflow = loader.load_workflow("burr_subsystem_demo")
    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)
    tool_registry = ToolRegistry()
    graph = GraphBuilder(model_registry, tool_registry).compile(workflow)
    state = initial_state(
        run_id="test-run",
        workflow_name=workflow.name,
        inputs={"message": "workflow"},
    )

    result = await graph.ainvoke(state)

    assert result["errors"] == []
    assert result["node_outputs"]["greet_with_burr"] == {
        "greeting": "Hello, workflow!",
        "status": "complete",
    }
    assert result["artifacts"]["greet_with_burr"]["burr_final_state"] == {
        "message": "workflow",
        "status": "complete",
        "greeting": "Hello, workflow!",
    }
    assert set(result["artifacts"]["greet_with_burr"]) == {
        "burr_final_state",
        "burr_final_state.json",
        "burr_node_metadata.json",
        "burr_trace.json",
    }


@pytest.mark.asyncio
async def test_burr_subsystem_node_result_references_json_artifacts() -> None:
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
        input_map={"message": "inputs.message"},
        output_map={"greeting": "greeting"},
        halt_after=["greet"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "artifacts"})

    result = await node.execute(node.create_context(state))

    assert result.artifact is not None
    assert result.artifact["burr_final_state.json"] == {
        "message": "artifacts",
        "status": "complete",
        "greeting": "Hello, artifacts!",
    }
    metadata = result.artifact["burr_node_metadata.json"]
    assert metadata["node_id"] == "burr_test"
    assert metadata["app_module"] == "app.subsystems.example_burr_app"
    assert metadata["app_factory"] == "build_example_app"
    assert metadata["status"] == "completed"
    assert metadata["duration_ms"] >= 0
    assert metadata["input_keys"] == ["message"]
    assert metadata["output_keys"] == ["greeting"]
    assert datetime.fromisoformat(metadata["started_at"]) <= datetime.fromisoformat(
        metadata["finished_at"]
    )
    assert result.artifact["burr_trace.json"] == {
        "source": "minimal",
        "events": [
            {
                "event": "start",
                "timestamp": metadata["started_at"],
                "state": {"message": "artifacts", "status": "initialized"},
            },
            {
                "event": "end",
                "timestamp": metadata["finished_at"],
                "status": "completed",
                "state": {
                    "message": "artifacts",
                    "status": "complete",
                    "greeting": "Hello, artifacts!",
                },
            },
        ],
        "final_state": result.artifact["burr_final_state.json"],
    }


@pytest.mark.asyncio
async def test_burr_subsystem_supports_terminal_states() -> None:
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
        input_map={"message": "inputs.message"},
        output_map={"greeting": "greeting"},
        terminal_states=["complete"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "terminal"})

    result = await node(state)

    assert result["errors"] == []
    assert result["node_outputs"]["burr_test"] == {"greeting": "Hello, terminal!"}


@pytest.mark.asyncio
async def test_burr_subsystem_records_failed_app_import() -> None:
    node = build_node(
        app_module="app.subsystems.missing_app",
        app_factory="build_app",
        input_map={},
        output_map={},
        halt_after=["done"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={})

    result = await node(state)

    assert result["node_outputs"] == {}
    assert_node_error(
        result,
        "burr_subsystem node 'burr_test' could not import app module "
        "'app.subsystems.missing_app': No module named 'app.subsystems.missing_app'",
    )


@pytest.mark.asyncio
async def test_burr_subsystem_records_missing_burr_dependency(monkeypatch) -> None:
    def missing_burr(_module_name: str):
        raise ModuleNotFoundError("No module named 'burr'")

    monkeypatch.setattr("app.nodes.burr_subsystem.import_module", missing_burr)
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
        halt_after=["greet"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={})

    result = await node(state)

    assert_node_error(
        result,
        "burr_subsystem node 'burr_test' requires Apache Burr. "
        "Install it with: pip install apache-burr",
    )


@pytest.mark.asyncio
async def test_burr_subsystem_records_missing_factory() -> None:
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="missing_factory",
        halt_after=["greet"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={})

    result = await node(state)

    assert_node_error(
        result,
        "burr_subsystem node 'burr_test' app module 'app.subsystems.example_burr_app' "
        "has no factory 'missing_factory'.",
    )


@pytest.mark.asyncio
async def test_burr_subsystem_records_factory_returning_non_runnable_object() -> None:
    node = build_node(
        app_module="app.subsystems.testing_burr_apps",
        app_factory="build_not_runnable",
        halt_after=["anything"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={})

    result = await node(state)

    assert_node_error(
        result,
        "burr_subsystem factory app.subsystems.testing_burr_apps.build_not_runnable "
        "did not return a runnable Burr ApplicationBuilder or application.",
    )


@pytest.mark.asyncio
async def test_burr_subsystem_records_missing_mapped_input() -> None:
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
        input_map={"message": "inputs.message"},
        halt_after=["greet"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={})

    result = await node(state)

    assert_node_error(
        result,
        "burr_subsystem node 'burr_test' could not map input 'message': "
        "parent workflow path 'inputs.message' was not found.",
    )


@pytest.mark.asyncio
async def test_burr_subsystem_records_missing_expected_output_and_final_state_artifact() -> None:
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
        input_map={"message": "inputs.message"},
        output_map={"missing": "missing"},
        halt_after=["greet"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "output"})

    result = await node(state)

    assert_node_error(
        result,
        "burr_subsystem node 'burr_test' could not map output 'missing': "
        "Burr final state path 'missing' was not found.",
    )
    assert result["artifacts"]["burr_test"]["burr_final_state"] == {
        "message": "output",
        "status": "complete",
        "greeting": "Hello, output!",
    }


@pytest.mark.asyncio
async def test_burr_subsystem_saves_latest_state_when_started_app_fails() -> None:
    node = build_node(
        app_module="app.subsystems.testing_burr_apps",
        app_factory="build_failing_app",
        input_map={"message": "inputs.message"},
        halt_after=["fail_after_start"],
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "run"})

    result = await node(state)

    assert_node_error(
        result,
        "burr_subsystem node 'burr_test' failed while running "
        "app.subsystems.testing_burr_apps.build_failing_app: intentional failure for run",
    )
    assert result["artifacts"]["burr_test"]["burr_final_state"] == {
        "message": "run",
        "status": "initialized",
    }


@pytest.mark.asyncio
async def test_burr_subsystem_saves_state_when_started_app_times_out() -> None:
    node = build_node(
        app_module="app.subsystems.testing_burr_apps",
        app_factory="build_slow_app",
        input_map={"message": "inputs.message"},
        halt_after=["finish_slowly"],
        timeout_seconds=0.001,
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "timeout"})

    result = await node(state)

    assert_node_error(result, "burr_subsystem node 'burr_test' timed out after 0.001s.")
    assert result["artifacts"]["burr_test"]["burr_final_state"] == {
        "message": "timeout",
        "status": "initialized",
    }


@pytest.mark.asyncio
async def test_burr_subsystem_supports_custom_artifact_name() -> None:
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
        input_map={"message": "inputs.message"},
        output_map={"greeting": "greeting"},
        halt_after=["greet"],
        artifact_name="child_snapshot",
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "artifact"})

    result = await node(state)

    assert result["artifacts"]["burr_test"]["child_snapshot"] == {
        "message": "artifact",
        "status": "complete",
        "greeting": "Hello, artifact!",
    }


@pytest.mark.asyncio
async def test_burr_subsystem_can_continue_when_fail_on_error_is_false() -> None:
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
        input_map={"message": "inputs.message"},
        output_map={"missing": "missing"},
        halt_after=["greet"],
        fail_on_error=False,
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "continue"})

    result = await node(state)

    assert result["errors"] == []
    assert result["node_outputs"]["burr_test"] == {}
    assert result["artifacts"]["burr_test"]["burr_final_state"]["greeting"] == "Hello, continue!"
