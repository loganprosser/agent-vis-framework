import pytest

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state


def build_graph():
    loader = ConfigLoader()
    workflow = loader.load_workflow("branching_burr_requirements")
    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)
    return workflow, GraphBuilder(model_registry, ToolRegistry()).compile(workflow)


async def run_workflow(requirements_text: str):
    workflow, graph = build_graph()
    state = initial_state(
        run_id="branching-test-run",
        workflow_name=workflow.name,
        inputs={"requirements_text": requirements_text},
    )
    return await graph.ainvoke(state)


@pytest.mark.asyncio
async def test_valid_requirements_skip_repair() -> None:
    result = await run_workflow("Users can export reports.")

    assert result["errors"] == []
    burr_output = result["node_outputs"]["validate_and_structure_requirements"]
    assert burr_output == {
        "structured_requirements": {
            "summary": "Users can export reports.",
            "validated": True,
            "repair_happened": False,
        },
        "validation_status": "valid",
    }
    final_state = result["artifacts"]["validate_and_structure_requirements"]["burr_final_state"]
    assert final_state["repair_happened"] is False
    assert final_state["validation_status"] == "valid"


@pytest.mark.asyncio
@pytest.mark.parametrize("requirements_text", ["", "short"])
async def test_invalid_requirements_enter_repair(requirements_text: str) -> None:
    result = await run_workflow(requirements_text)

    assert result["errors"] == []
    burr_output = result["node_outputs"]["validate_and_structure_requirements"]
    assert set(burr_output) == {"structured_requirements", "validation_status"}
    assert burr_output["validation_status"] == "repaired"
    assert burr_output["structured_requirements"]["repair_happened"] is True
    final_state = result["artifacts"]["validate_and_structure_requirements"]["burr_final_state"]
    assert final_state["repair_happened"] is True
    assert final_state["validation_status"] == "repaired"
    assert len(final_state["raw_requirements"]) >= 12
    trace = result["artifacts"]["validate_and_structure_requirements"]["burr_trace.json"]
    assert trace["source"] == "burr_lifecycle_hooks"
    assert [
        event["action"]
        for event in trace["events"]
        if event["event"] == "action_end"
    ] == [
        "validate_requirements",
        "repair_requirements",
        "structure_requirements",
    ]
