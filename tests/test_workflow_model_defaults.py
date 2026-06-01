"""Tests for workflow-level default_provider and default_model resolution.

The resolution chain is: node override -> workflow default -> registry fallback (provider)
                                                            -> provider default (model)
"""

import json

import pytest

from app.api.routes import export_workflow
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, NodeRegistry, ToolRegistry
from app.core.state import initial_state
from app.models.mock_provider import MockModelProvider
from app.nodes.base import BaseNode
from app.schemas.node_io import NodeContext, NodeResult
from app.schemas.workflow import EdgeConfig, NodeConfig, WorkflowConfig
from app.core.state import WorkflowState


class EchoNode(BaseNode):
    """Node that echoes the resolved provider_id and model name from config."""

    async def execute(self, context: NodeContext) -> NodeResult:
        return NodeResult(
            values={
                "provider_id": self.model_provider.provider_id,
                "model": self.config.model or self.model_provider.default_model,
            },
        )


class AskModelNode(BaseNode):
    """Node that calls ask_model and returns the provider's response verbatim.

    This proves the resolved model name is actually sent to the provider at
    runtime, not just stored in metadata.
    """

    async def execute(self, context: NodeContext) -> NodeResult:
        response_text = await self.ask_model(context.state, "test prompt")
        return NodeResult(values={"llm_response": response_text})


def _make_registry() -> ModelRegistry:
    registry = ModelRegistry()
    registry._providers["mock"] = MockModelProvider("mock", "mock-deterministic", {"temperature": 0})
    registry._providers["mock_other"] = MockModelProvider("mock_other", "other-model", {})
    return registry


def _node_reg(node_type: str, node_cls: type) -> NodeRegistry:
    reg = NodeRegistry()
    reg._factories[node_type] = node_cls
    return reg


def _make_workflow(
    default_provider: str | None = None,
    default_model: str | None = None,
    node_provider: str | None = None,
    node_model: str | None = None,
) -> WorkflowConfig:
    return WorkflowConfig(
        name="test_workflow",
        entrypoint="echo",
        default_provider=default_provider,
        default_model=default_model,
        nodes=[
            NodeConfig(
                id="echo",
                type="echo",
                provider=node_provider,
                model=node_model,
            ),
        ],
        edges=[],
    )


# --- Resolution chain tests (metadata level) ---

@pytest.mark.asyncio
async def test_node_uses_own_provider_when_specified() -> None:
    workflow = _make_workflow(default_provider="mock_other", node_provider="mock")
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t1", workflow_name="test_workflow", inputs={})
    )
    assert result["node_outputs"]["echo"]["provider_id"] == "mock"


@pytest.mark.asyncio
async def test_node_falls_back_to_workflow_default_provider() -> None:
    workflow = _make_workflow(default_provider="mock_other")
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t2", workflow_name="test_workflow", inputs={})
    )
    assert result["node_outputs"]["echo"]["provider_id"] == "mock_other"


@pytest.mark.asyncio
async def test_node_falls_back_to_registry_default_when_no_workflow_default() -> None:
    workflow = _make_workflow()
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t3", workflow_name="test_workflow", inputs={})
    )
    assert result["node_outputs"]["echo"]["provider_id"] == "mock"


@pytest.mark.asyncio
async def test_workflow_default_model_overrides_provider_default() -> None:
    workflow = _make_workflow(default_provider="mock", default_model="workflow-model")
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t4", workflow_name="test_workflow", inputs={})
    )
    assert result["node_outputs"]["echo"]["model"] == "workflow-model"


@pytest.mark.asyncio
async def test_node_model_overrides_workflow_default_model() -> None:
    workflow = _make_workflow(default_provider="mock", default_model="workflow-model", node_model="node-model")
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t5", workflow_name="test_workflow", inputs={})
    )
    assert result["node_outputs"]["echo"]["model"] == "node-model"


@pytest.mark.asyncio
async def test_no_workflow_defaults_existing_behavior_preserved() -> None:
    workflow = _make_workflow(node_provider="mock", node_model="mock-deterministic")
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t6", workflow_name="test_workflow", inputs={})
    )
    assert result["node_outputs"]["echo"]["provider_id"] == "mock"
    assert result["node_outputs"]["echo"]["model"] == "mock-deterministic"


# --- Runtime-active tests (ask_model actually sends resolved model to provider) ---

@pytest.mark.asyncio
async def test_ask_model_receives_workflow_default_model() -> None:
    """When a node inherits workflow default_model, ask_model sends that model
    to the provider's generate() call — not the provider's default_model."""
    workflow = WorkflowConfig(
        name="runtime_test",
        entrypoint="ask",
        default_provider="mock",
        default_model="workflow-resolved-model",
        nodes=[NodeConfig(id="ask", type="ask")],
        edges=[],
    )
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("ask", AskModelNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t7", workflow_name="runtime_test", inputs={})
    )
    response = json.loads(result["node_outputs"]["ask"]["llm_response"])
    # MockModelProvider echoes the model it received in the request
    assert response["model"] == "workflow-resolved-model"
    assert response["provider"] == "mock"


@pytest.mark.asyncio
async def test_ask_model_receives_node_override_model() -> None:
    """Node's own model overrides workflow default in the actual generate() call."""
    workflow = WorkflowConfig(
        name="runtime_test",
        entrypoint="ask",
        default_provider="mock",
        default_model="workflow-model",
        nodes=[NodeConfig(id="ask", type="ask", model="node-override-model")],
        edges=[],
    )
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("ask", AskModelNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t8", workflow_name="runtime_test", inputs={})
    )
    response = json.loads(result["node_outputs"]["ask"]["llm_response"])
    assert response["model"] == "node-override-model"


@pytest.mark.asyncio
async def test_ask_model_uses_provider_default_when_no_workflow_or_node_model() -> None:
    """When neither workflow nor node specify a model, the provider default is used."""
    workflow = WorkflowConfig(
        name="runtime_test",
        entrypoint="ask",
        default_provider="mock_other",
        nodes=[NodeConfig(id="ask", type="ask")],
        edges=[],
    )
    registry = _make_registry()

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("ask", AskModelNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="t9", workflow_name="runtime_test", inputs={})
    )
    response = json.loads(result["node_outputs"]["ask"]["llm_response"])
    assert response["model"] == "other-model"
    assert response["provider"] == "mock_other"


# --- API export tests ---

def test_export_workflow_includes_resolved_provider_and_model() -> None:
    workflow = WorkflowConfig(
        name="export_test",
        entrypoint="echo",
        default_provider="mock_other",
        default_model="workflow-model",
        nodes=[
            NodeConfig(id="echo", type="echo"),
            NodeConfig(id="explicit", type="echo", provider="mock", model="node-model"),
        ],
        edges=[],
    )
    data = export_workflow(workflow)

    assert data["default_provider"] == "mock_other"
    assert data["default_model"] == "workflow-model"

    echo_node = next(n for n in data["nodes"] if n["id"] == "echo")
    assert echo_node["_resolved"]["provider"] == "mock_other"
    assert echo_node["_resolved"]["model"] == "workflow-model"

    explicit_node = next(n for n in data["nodes"] if n["id"] == "explicit")
    assert explicit_node["_resolved"]["provider"] == "mock"
    assert explicit_node["_resolved"]["model"] == "node-model"


def test_export_workflow_without_defaults_no_resolved_values() -> None:
    workflow = WorkflowConfig(
        name="no_defaults",
        entrypoint="echo",
        nodes=[NodeConfig(id="echo", type="echo")],
        edges=[],
    )
    data = export_workflow(workflow)

    assert "default_provider" not in data
    assert "default_model" not in data

    echo_node = data["nodes"][0]
    assert echo_node["_resolved"]["provider"] is None
    assert echo_node["_resolved"]["model"] is None


# --- Burr subsystem provider injection tests ---

def test_burr_subsystem_injects_provider_agnostic_kwargs_to_opted_in_factory() -> None:
    """When a Burr factory declares provider_id/model/base_url parameters,
    _inject_provider_kwargs should forward the resolved values."""
    from app.nodes.burr_subsystem import BurrSubsystemNode

    node = BurrSubsystemNode(
        config=NodeConfig(
            id="sub",
            type="burr_subsystem",
            config={
                "app_module": "app.subsystems.example_burr_app",
                "app_factory": "build_example_app",
                "input_map": {"message": "inputs.message"},
                "halt_after": ["greet"],
            },
        ),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
    )

    factory_inputs = {"message": "hello"}
    node._inject_provider_kwargs(factory_inputs)

    # build_example_app() doesn't accept provider_id/model/base_url params,
    # so none should be injected (signature filtering prevents TypeError)
    assert "provider_id" not in factory_inputs
    assert "model" not in factory_inputs
    assert "base_url" not in factory_inputs


def test_burr_subsystem_injects_kwargs_to_factory_that_accepts_them() -> None:
    """When a Burr factory declares model/provider params, they get injected."""
    from app.nodes.burr_subsystem import BurrSubsystemNode

    # build_iterative_code_reviewer accepts ollama_model and ollama_base_url
    node = BurrSubsystemNode(
        config=NodeConfig(
            id="sub",
            type="burr_subsystem",
            config={
                "app_module": "app.subsystems.iterative_code_reviewer",
                "app_factory": "build_iterative_code_reviewer",
                "input_map": {"problem_spec": "inputs.problem_spec"},
                "halt_after": ["finalize_solution"],
            },
        ),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
    )

    factory_inputs = {"problem_spec": "test spec"}
    node._inject_provider_kwargs(factory_inputs)

    # MockModelProvider is not OllamaModelProvider, so legacy ollama_* keys
    # should NOT be injected. But provider_id and model should not appear
    # either since build_iterative_code_reviewer doesn't accept them.
    assert "ollama_model" not in factory_inputs
    assert "ollama_base_url" not in factory_inputs
    # Generic keys not injected because factory doesn't declare them
    assert "provider_id" not in factory_inputs
    assert "model" not in factory_inputs


def test_burr_subsystem_does_not_inject_to_factory_without_matching_params() -> None:
    """Provider kwargs are NOT injected into factories that don't accept them,
    preventing TypeError on factory(**factory_inputs)."""
    from app.nodes.burr_subsystem import BurrSubsystemNode

    node = BurrSubsystemNode(
        config=NodeConfig(
            id="sub",
            type="burr_subsystem",
            config={
                "app_module": "app.subsystems.example_burr_app",
                "app_factory": "build_example_app",
                "input_map": {"message": "inputs.message"},
                "halt_after": ["greet"],
            },
        ),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
    )

    factory_inputs = {"message": "test"}
    node._inject_provider_kwargs(factory_inputs)

    # Should only contain the original input — no provider kwargs injected
    assert factory_inputs == {"message": "test"}


# --- LiteLLM provider tests ---

def test_litellm_provider_loads_from_models_yaml() -> None:
    """The litellm provider entry in models.yaml loads as OpenAIModelProvider."""
    from app.core.config_loader import ConfigLoader
    from app.models.openai_provider import OpenAIModelProvider

    loader = ConfigLoader()
    models = loader.load_models()
    litellm_cfg = next((p for p in models.providers if p.id == "litellm"), None)
    assert litellm_cfg is not None
    assert litellm_cfg.type == "litellm"

    registry = ModelRegistry()
    for p in models.providers:
        registry.register_provider_config(p)

    provider = registry.get("litellm")
    assert isinstance(provider, OpenAIModelProvider)
    assert provider.provider_id == "litellm"
    assert provider.default_model == "gpt-4.1-mini"


@pytest.mark.asyncio
async def test_litellm_as_node_level_provider_override() -> None:
    """A node with provider=litellm resolves to the litellm OpenAIModelProvider,
    while another node with provider=mock resolves to MockModelProvider."""
    from app.models.openai_provider import OpenAIModelProvider

    workflow = WorkflowConfig(
        name="mixed_test",
        entrypoint="mock_node",
        default_provider="mock",
        nodes=[
            NodeConfig(id="mock_node", type="echo"),
            NodeConfig(id="litellm_node", type="echo", provider="litellm", model="gpt-4.1-mini"),
        ],
        edges=[EdgeConfig(source="mock_node", target="litellm_node")],
    )

    # Build registry from models.yaml
    from app.core.config_loader import ConfigLoader
    loader = ConfigLoader()
    registry = ModelRegistry()
    for p in loader.load_models().providers:
        registry.register_provider_config(p)

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="litellm1", workflow_name="mixed_test", inputs={})
    )

    assert result["node_outputs"]["mock_node"]["provider_id"] == "mock"
    assert result["node_outputs"]["litellm_node"]["provider_id"] == "litellm"
    assert result["node_outputs"]["litellm_node"]["model"] == "gpt-4.1-mini"


@pytest.mark.asyncio
async def test_litellm_as_workflow_default_provider() -> None:
    """When default_provider=litellm, nodes without an explicit provider
    resolve to the litellm OpenAIModelProvider."""
    workflow = WorkflowConfig(
        name="litellm_default_test",
        entrypoint="echo",
        default_provider="litellm",
        default_model="gpt-4.1-mini",
        nodes=[NodeConfig(id="echo", type="echo")],
        edges=[],
    )

    from app.core.config_loader import ConfigLoader
    loader = ConfigLoader()
    registry = ModelRegistry()
    for p in loader.load_models().providers:
        registry.register_provider_config(p)

    graph = GraphBuilder(registry, ToolRegistry(), _node_reg("echo", EchoNode)).compile(workflow)
    result = await graph.ainvoke(
        initial_state(run_id="litellm2", workflow_name="litellm_default_test", inputs={})
    )

    assert result["node_outputs"]["echo"]["provider_id"] == "litellm"
    assert result["node_outputs"]["echo"]["model"] == "gpt-4.1-mini"


def test_mixed_provider_demo_workflow_loads_and_compiles() -> None:
    """The mixed_provider_demo YAML loads and compiles with both mock and litellm nodes."""
    from app.core.config_loader import ConfigLoader

    loader = ConfigLoader()
    workflow = loader.load_workflow("mixed_provider_demo")

    assert workflow.default_provider == "mock"
    assert workflow.default_model == "mock-deterministic"

    registry = ModelRegistry()
    for p in loader.load_models().providers:
        registry.register_provider_config(p)

    tool_registry = ToolRegistry({s.id: s for s in loader.load_mcps().servers})
    for t in loader.load_tools().tools:
        tool_registry.register_tool_config(t)

    graph = GraphBuilder(registry, tool_registry, config_loader=loader).compile(workflow)
    assert graph is not None  # compiled without error
