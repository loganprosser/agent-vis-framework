import pytest

from app.core.graph_builder import default_node_registry
from app.core.registry import NodeRegistry
from app.core.run_store import RunStore
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


class FailingNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        raise RuntimeError("intentional node failure")


class BrokenEventStore:
    def append_event(self, *args, **kwargs):
        raise RuntimeError("event store unavailable")


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
        "problem_analyzer",
        "react_orchestrator",
        "report_generator",
        "requirements_report",
        "solution_presenter",
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


@pytest.mark.asyncio
async def test_failing_node_emits_node_failed_event() -> None:
    store = RunStore()
    node = FailingNode(
        config=NodeConfig(id="failing", type="failing"),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
        event_store=store,
    )
    state = initial_state(run_id="failing-run", workflow_name="test", inputs={})

    result = await node(state)

    assert result["errors"] == [{"node_id": "failing", "message": "intentional node failure"}]
    assert [event.event_type for event in store.list_events("failing-run")] == [
        "node_started",
        "node_failed",
    ]
    assert store.list_events("failing-run")[1].payload["error"] == "intentional node failure"


@pytest.mark.asyncio
async def test_event_logging_failure_does_not_fail_node_execution() -> None:
    node = ContextAwareNode(
        config=NodeConfig(id="context_aware", type="context_aware", input_keys=["message"]),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
        event_store=BrokenEventStore(),
    )
    state = initial_state(run_id="test-run", workflow_name="test", inputs={"message": "hello"})

    result = await node(state)

    assert result["errors"] == []
    assert result["node_outputs"]["context_aware"] == {"message": "hello"}
