import pytest

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state


@pytest.mark.asyncio
async def test_mixed_workflow_runs_normal_nodes_around_burr_subsystem() -> None:
    loader = ConfigLoader()
    workflow = loader.load_workflow("mixed_burr_requirements")
    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)
    graph = GraphBuilder(model_registry, ToolRegistry()).compile(workflow)
    state = initial_state(
        run_id="mixed-test-run",
        workflow_name=workflow.name,
        inputs={"requirements_text": "  Users   can export reports.  "},
    )

    result = await graph.ainvoke(state)

    assert result["errors"] == []
    assert [log for log in result["logs"] if log.endswith(": completed")] == [
        "requirements_input: completed",
        "refine_requirements: completed",
        "requirements_report: completed",
    ]
    structured_requirements = {
        "summary": "Users can export reports.",
        "validated": True,
        "requirement_count": 1,
    }
    assert result["artifacts"]["refine_requirements"]["burr_final_state"] == {
        "raw_requirements": "  Users   can export reports.  ",
        "status": "complete",
        "structured_requirements": structured_requirements,
    }
    assert result["artifacts"]["refine_requirements"]["burr_final_state.json"] == (
        result["artifacts"]["refine_requirements"]["burr_final_state"]
    )
    assert result["artifacts"]["refine_requirements"]["burr_node_metadata.json"]["status"] == (
        "completed"
    )
    assert result["artifacts"]["refine_requirements"]["burr_trace.json"]["source"] == (
        "burr_lifecycle_hooks"
    )
    assert result["node_outputs"]["refine_requirements"]["structured_requirements"] == (
        structured_requirements
    )
    assert result["node_outputs"]["requirements_report"]["structured_requirements"] == (
        structured_requirements
    )
    assert result["artifacts"]["requirements_report"] == {
        "type": "requirements_summary",
        "summary": result["final_report"],
    }
