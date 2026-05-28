import pytest

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state


@pytest.mark.asyncio
async def test_compiles_and_runs_example_workflow() -> None:
    loader = ConfigLoader()
    workflow = loader.load_workflow("combinatorial_test_generation")

    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)

    tool_registry = ToolRegistry()
    for tool in loader.load_tools().tools:
        tool_registry.register_tool_config(tool)

    graph = GraphBuilder(model_registry, tool_registry).compile(workflow)
    state = initial_state(
        run_id="test-run",
        workflow_name=workflow.name,
        inputs={"requirements_doc": "requirements.md", "source_path": "src"},
    )

    result = await graph.ainvoke(state)

    assert result["errors"] == []
    assert result["node_outputs"]["tnt_cli_reducer"]["reduced_test_set"]
    assert "Combinatorial Test Generation Report" in result["final_report"]
