import pytest

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
    assert result["errors"] == [
        {
            "node_id": "burr_test",
            "message": (
                "burr_subsystem could not import app module 'app.subsystems.missing_app': "
                "No module named 'app.subsystems.missing_app'"
            ),
        }
    ]


@pytest.mark.asyncio
async def test_burr_subsystem_records_missing_burr_dependency(monkeypatch) -> None:
    def missing_burr(_module_name: str):
        raise ModuleNotFoundError("No module named 'burr'")

    monkeypatch.setattr("app.nodes.burr_subsystem.import_module", missing_burr)
    node = build_node(
        app_module="app.subsystems.example_burr_app",
        app_factory="build_example_app",
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={})

    result = await node(state)

    assert result["errors"] == [
        {
            "node_id": "burr_test",
            "message": (
                "burr_subsystem requires Apache Burr. "
                "Install it with: pip install apache-burr"
            ),
        }
    ]
