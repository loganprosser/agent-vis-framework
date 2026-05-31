import pytest

from app.core.graph_builder import default_node_registry
from app.core.registry import NodeRegistry
from app.core.state import WorkflowState, initial_state
from app.models.mock_provider import MockModelProvider
from app.nodes.base import BaseNode
from app.schemas.node_io import NodeContext, NodeResult
from app.schemas.workflow import NodeConfig


class ContextAwareNode(BaseNode):
    async def execute(self, context: NodeContext) -> NodeResult:
        return NodeResult(values={"message": context.values["message"]}, logs=["context-aware log"])

    async def run(self, state: WorkflowState) -> dict:
        raise AssertionError("execute() should be the pluggable node boundary")


def test_default_registry_contains_existing_node_types() -> None:
    registry = default_node_registry()

    assert registry.registered_types() == [
        "burr_subsystem",
        "constraint_builder",
        "doc_reader",
        "domain_generator",
        "mcp_call",
        "mcp_discovery",
        "mock_requirements_input",
        "report_generator",
        "requirements_report",
        "source_reader",
        "test_runner",
        "test_validator",
        "test_writer",
        "tnt_cli_reducer",
        "variable_classifier",
        "variable_extractor",
    ]


@pytest.mark.asyncio
async def test_registry_runs_context_aware_node_result() -> None:
    registry = NodeRegistry()
    registry.register("context_aware", ContextAwareNode)
    node = registry.create(
        "context_aware",
        config=NodeConfig(id="context_aware", type="context_aware", input_keys=["message"]),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "hello"})

    result = await node(state)

    assert result["node_outputs"]["context_aware"] == {"message": "hello"}
    assert result["artifacts"]["context_aware"] == {"message": "hello"}
    assert result["logs"] == ["context-aware log", "context_aware: completed"]
