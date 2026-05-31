import pytest

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state


def build_graph(workflow_name: str):
    loader = ConfigLoader()
    workflow = loader.load_workflow(workflow_name)

    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)

    tool_registry = ToolRegistry({server.id: server for server in loader.load_mcps().servers})
    for tool in loader.load_tools().tools:
        tool_registry.register_tool_config(tool)

    return workflow, GraphBuilder(model_registry, tool_registry).compile(workflow)


@pytest.mark.asyncio
async def test_compiles_and_runs_example_workflow() -> None:
    workflow, graph = build_graph("combinatorial_test_generation")
    state = initial_state(
        run_id="test-run",
        workflow_name=workflow.name,
        inputs={"requirements_doc": "requirements.md", "source_path": "src"},
    )

    result = await graph.ainvoke(state)

    assert result["errors"] == []
    assert result["node_outputs"]["tnt_cli_reducer"]["reduced_test_set"]
    assert "Combinatorial Test Generation Report" in result["final_report"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workflow_name", "inputs"),
    [
        ("starter_three_node", {"requirements_doc": "requirements.md"}),
        ("mcp_discovery_demo", {}),
    ],
)
async def test_compiles_and_runs_existing_workflows(workflow_name: str, inputs: dict) -> None:
    workflow, graph = build_graph(workflow_name)
    state = initial_state(run_id="test-run", workflow_name=workflow.name, inputs=inputs)

    result = await graph.ainvoke(state)

    assert result["errors"] == []
    assert set(result["node_outputs"]) == {node.id for node in workflow.nodes}
