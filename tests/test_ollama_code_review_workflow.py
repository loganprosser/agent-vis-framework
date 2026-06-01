"""Tests for the ollama_iterative_code_review workflow.

Covers:
  - YAML config loading and Pydantic validation
  - Burr app unit tests (mock model, no Ollama required)
  - Node unit tests (mock model provider)
  - Full workflow graph compilation and end-to-end run (monkeypatched Ollama)
  - Live Ollama integration test (skipped when Ollama is not reachable)
"""
from __future__ import annotations

import socket
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state
from app.models.base import ModelResponse
from app.models.mock_provider import MockModelProvider
from app.nodes.burr_subsystem import BurrSubsystemNode
from app.nodes.problem_analyzer import ProblemAnalyzerNode
from app.nodes.solution_presenter import SolutionPresenterNode
from app.schemas.workflow import NodeConfig
from app.subsystems.iterative_code_reviewer import (
    ACCEPT_THRESHOLD,
    _parse_quality_score,
    build_iterative_code_reviewer,
)

WORKFLOW_NAME = "ollama_iterative_code_review"
SAMPLE_PROBLEM = "Write a Python function that returns all prime numbers up to N."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_provider() -> MockModelProvider:
    return MockModelProvider("mock", "mock-deterministic")


def _build_burr_node(**extra_config) -> BurrSubsystemNode:
    config = {
        "app_module": "app.subsystems.iterative_code_reviewer",
        "app_factory": "build_iterative_code_reviewer",
        "input_map": {"problem_spec": "inputs.problem_spec"},
        "output_map": {
            "final_solution": "final_solution",
            "final_score": "final_score",
            "iterations_used": "iterations_used",
            "accepted": "accepted",
        },
        "halt_after": ["finalize_solution"],
        **extra_config,
    }
    return BurrSubsystemNode(
        config=NodeConfig(id="iterative_solve", type="burr_subsystem", config=config),
        model_provider=_mock_provider(),
    )


def _make_mock_model(responses: list[str]):
    """Return a call_model callable that cycles through the given responses."""
    it = iter(responses)

    def mock_model(system_prompt: str, user_message: str) -> str:  # noqa: ARG001
        try:
            return next(it)
        except StopIteration:
            return f"Quality score: {ACCEPT_THRESHOLD}/10"

    return mock_model


def _ollama_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=1):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Config / schema
# ---------------------------------------------------------------------------


def test_workflow_config_loads_and_validates() -> None:
    workflow = ConfigLoader().load_workflow(WORKFLOW_NAME)
    assert workflow.name == WORKFLOW_NAME
    assert workflow.entrypoint == "analyze_problem"
    assert {n.id for n in workflow.nodes} == {
        "analyze_problem",
        "iterative_solve",
        "present_solution",
    }


def test_workflow_burr_config_defaults_are_applied() -> None:
    workflow = ConfigLoader().load_workflow(WORKFLOW_NAME)
    burr_node = next(n for n in workflow.nodes if n.id == "iterative_solve")
    assert burr_node.config["artifact_name"] == "burr_final_state"
    assert burr_node.config["fail_on_error"] is True
    assert burr_node.config["halt_after"] == ["finalize_solution"]


def test_workflow_topology_is_present_and_valid() -> None:
    workflow = ConfigLoader().load_workflow(WORKFLOW_NAME)
    burr_node = next(n for n in workflow.nodes if n.id == "iterative_solve")
    topology = burr_node.config["topology"]
    action_ids = {a["id"] for a in topology["actions"]}
    assert action_ids == {"draft_solution", "critique_solution", "evaluate_quality", "finalize_solution"}
    assert topology["entrypoint"] == "draft_solution"


def test_workflow_compiles_with_mock_registry() -> None:
    loader = ConfigLoader()
    workflow = loader.load_workflow(WORKFLOW_NAME)
    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)
    tool_registry = ToolRegistry()
    graph = GraphBuilder(model_registry, tool_registry, config_loader=loader).compile(workflow)
    assert graph is not None


# ---------------------------------------------------------------------------
# _parse_quality_score unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Quality score: 8/10", 8),
        ("Score: 7/10", 7),
        ("quality score: 10/10", 10),
        ("I give it 6/10", 6),
        ("score: 3", 3),
        ("quality: 9", 9),
        ("no score here at all", 5),  # fallback
        ("score: 11", 5),             # out of range → fallback
    ],
)
def test_parse_quality_score(text: str, expected: int) -> None:
    assert _parse_quality_score(text) == expected


# ---------------------------------------------------------------------------
# Burr app unit tests (no Ollama)
# ---------------------------------------------------------------------------


def test_burr_app_accepts_immediately_when_score_is_high() -> None:
    mock = _make_mock_model([
        "def primes(n): ...",                         # draft
        f"Looks great. Quality score: {ACCEPT_THRESHOLD}/10",  # critique → accepted
    ])
    app = build_iterative_code_reviewer(
        SAMPLE_PROBLEM, max_iterations=3, _override_call_model=mock
    ).build()

    _, _, final_state = app.run(halt_after=["finalize_solution"])

    assert final_state["accepted"] is True
    assert final_state["iterations_used"] == 1
    assert final_state["final_score"] == ACCEPT_THRESHOLD
    assert final_state["status"] == "complete"


def test_burr_app_loops_when_score_is_below_threshold() -> None:
    call_log: list[str] = []

    def tracking_model(system_prompt: str, user_message: str) -> str:
        call_log.append("draft" if "write" in system_prompt.lower() or "revise" in user_message.lower() else "critique")
        if len(call_log) <= 2:
            return "def bad(): pass\nQuality score: 3/10"
        return f"Much better. Quality score: {ACCEPT_THRESHOLD}/10"

    app = build_iterative_code_reviewer(
        SAMPLE_PROBLEM, max_iterations=3, _override_call_model=tracking_model
    ).build()

    _, _, final_state = app.run(halt_after=["finalize_solution"])

    assert final_state["iterations_used"] >= 2
    assert final_state["status"] == "complete"


def test_burr_app_stops_at_max_iterations_when_score_stays_low() -> None:
    low_score_model = _make_mock_model(
        ["def bad(): pass", "Score: 2/10"] * 10
    )
    max_iter = 2
    app = build_iterative_code_reviewer(
        SAMPLE_PROBLEM, max_iterations=max_iter, _override_call_model=low_score_model
    ).build()

    _, _, final_state = app.run(halt_after=["finalize_solution"])

    assert final_state["iterations_used"] == max_iter
    assert final_state["accepted"] is False
    assert final_state["status"] == "complete"


def test_burr_app_incorporates_critique_on_second_draft() -> None:
    messages_seen: list[str] = []

    def recording_model(system_prompt: str, user_message: str) -> str:
        messages_seen.append(user_message)
        if len(messages_seen) == 1:
            return "def v1(): pass"
        if len(messages_seen) == 2:
            return "Needs better edge case handling. Quality score: 4/10"
        if len(messages_seen) == 3:
            return "def v2(): pass"
        return f"Great. Quality score: {ACCEPT_THRESHOLD}/10"

    app = build_iterative_code_reviewer(
        SAMPLE_PROBLEM, max_iterations=3, _override_call_model=recording_model
    ).build()
    app.run(halt_after=["finalize_solution"])

    # Third call should contain the critique text from second call
    assert "Needs better edge case handling" in messages_seen[2]


@pytest.mark.asyncio
async def test_burr_app_emits_expected_trace_events(monkeypatch) -> None:
    from app.core.run_store import RunStore

    def mock_ollama(system_prompt, user_message, *, model, base_url, **kw):  # noqa: ANN001
        if "reviewer" in system_prompt.lower() or "critique" in system_prompt.lower():
            return f"Quality score: {ACCEPT_THRESHOLD}/10"
        return "def primes(n): pass"

    monkeypatch.setattr(
        "app.subsystems.iterative_code_reviewer._call_ollama_sync",
        mock_ollama,
    )

    node = _build_burr_node()
    event_store = RunStore()
    node.event_store = event_store

    state = initial_state(
        run_id="trace-test",
        workflow_name=WORKFLOW_NAME,
        inputs={"problem_spec": SAMPLE_PROBLEM},
    )

    await node(state)

    event_types = [e.event_type for e in event_store.list_events("trace-test")]
    assert "node_started" in event_types
    assert "burr_subsystem_started" in event_types
    assert "burr_action_started" in event_types
    assert "node_completed" in event_types


# ---------------------------------------------------------------------------
# Node unit tests (mock model provider)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_problem_analyzer_node_returns_spec_and_raw_problem() -> None:
    node = ProblemAnalyzerNode(
        config=NodeConfig(id="analyze_problem", type="problem_analyzer"),
        model_provider=_mock_provider(),
    )
    state = initial_state(
        run_id="test", workflow_name=WORKFLOW_NAME, inputs={"problem": SAMPLE_PROBLEM}
    )
    result = await node.run(state)

    assert result["raw_problem"] == SAMPLE_PROBLEM
    assert isinstance(result["problem_spec"], str)
    assert len(result["problem_spec"]) > 0


@pytest.mark.asyncio
async def test_solution_presenter_node_returns_final_report() -> None:
    node = SolutionPresenterNode(
        config=NodeConfig(id="present_solution", type="solution_presenter"),
        model_provider=_mock_provider(),
    )
    solver_output = {
        "final_solution": "def primes(n): return [p for p in range(2, n+1) if all(p%i != 0 for i in range(2,p))]",
        "final_score": 8,
        "iterations_used": 2,
        "accepted": True,
    }
    state = initial_state(run_id="test", workflow_name=WORKFLOW_NAME, inputs={})
    state["node_outputs"] = {"iterative_solve": solver_output}

    result = await node.run(state)

    assert "final_report" in result
    assert result["accepted"] is True
    assert result["iterations"] == 2
    assert result["quality_score"] == 8


@pytest.mark.asyncio
async def test_solution_presenter_node_handles_missing_solver_output() -> None:
    node = SolutionPresenterNode(
        config=NodeConfig(id="present_solution", type="solution_presenter"),
        model_provider=_mock_provider(),
    )
    state = initial_state(run_id="test", workflow_name=WORKFLOW_NAME, inputs={})

    result = await node.run(state)

    assert "final_report" in result
    assert result["accepted"] is False
    assert result["iterations"] == 0


# ---------------------------------------------------------------------------
# Full workflow end-to-end (Ollama monkeypatched)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_workflow_runs_end_to_end(monkeypatch) -> None:
    """Run the complete 3-node workflow with all Ollama calls monkeypatched."""

    def mock_ollama_provider(self, request):  # noqa: ANN001
        return ModelResponse(
            text="Mock analysis: the problem requires a sieve implementation.",
            raw={"provider": "mock"},
        )

    call_count = {"n": 0}

    def mock_burr_ollama(system_prompt, user_message, *, model, base_url, **kw):  # noqa: ANN001
        call_count["n"] += 1
        if "reviewer" in system_prompt.lower() or "critique" in system_prompt.lower():
            return f"Looks good. Quality score: {ACCEPT_THRESHOLD}/10"
        return "def sieve(n):\n    sieve = [True] * (n + 1)\n    ..."

    monkeypatch.setattr(
        "app.models.ollama_provider.OllamaModelProvider._generate_sync",
        mock_ollama_provider,
    )
    monkeypatch.setattr(
        "app.subsystems.iterative_code_reviewer._call_ollama_sync",
        mock_burr_ollama,
    )

    loader = ConfigLoader()
    workflow = loader.load_workflow(WORKFLOW_NAME)
    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)
    tool_registry = ToolRegistry()
    graph = GraphBuilder(model_registry, tool_registry, config_loader=loader).compile(workflow)

    state = initial_state(
        run_id="e2e-test",
        workflow_name=WORKFLOW_NAME,
        inputs={"problem": SAMPLE_PROBLEM},
    )
    result = await graph.ainvoke(state)

    assert result["errors"] == [], f"Unexpected errors: {result['errors']}"
    assert set(result["node_outputs"]) == {"analyze_problem", "iterative_solve", "present_solution"}
    assert result["node_outputs"]["analyze_problem"]["raw_problem"] == SAMPLE_PROBLEM
    assert "final_solution" in result["node_outputs"]["iterative_solve"]
    assert result["node_outputs"]["iterative_solve"]["accepted"] is True
    assert result["final_report"] is not None
    # Burr called Ollama at least twice (draft + critique)
    assert call_count["n"] >= 2


@pytest.mark.asyncio
async def test_full_workflow_burr_subsystem_emits_trace_artifacts(monkeypatch) -> None:
    """Verify the Burr node produces the three expected JSON artifact keys."""

    def mock_ollama_provider(self, request):  # noqa: ANN001
        return ModelResponse(text="Mock spec.", raw={})

    def mock_burr_ollama(system_prompt, user_message, *, model, base_url, **kw):  # noqa: ANN001
        if "reviewer" in system_prompt.lower() or "critique" in system_prompt.lower():
            return f"Quality score: {ACCEPT_THRESHOLD}/10"
        return "def solution(): pass"

    monkeypatch.setattr(
        "app.models.ollama_provider.OllamaModelProvider._generate_sync",
        mock_ollama_provider,
    )
    monkeypatch.setattr(
        "app.subsystems.iterative_code_reviewer._call_ollama_sync",
        mock_burr_ollama,
    )

    loader = ConfigLoader()
    workflow = loader.load_workflow(WORKFLOW_NAME)
    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)
    graph = GraphBuilder(model_registry, ToolRegistry(), config_loader=loader).compile(workflow)
    state = initial_state(run_id="artifact-test", workflow_name=WORKFLOW_NAME, inputs={"problem": SAMPLE_PROBLEM})

    result = await graph.ainvoke(state)

    burr_artifacts = result["artifacts"]["iterative_solve"]
    assert "burr_final_state.json" in burr_artifacts
    assert "burr_node_metadata.json" in burr_artifacts
    assert "burr_trace.json" in burr_artifacts
    trace = burr_artifacts["burr_trace.json"]
    assert trace["source"] == "burr_lifecycle_hooks"
    action_names = [e["action"] for e in trace["events"] if e["event"] == "action_start"]
    assert "draft_solution" in action_names
    assert "critique_solution" in action_names
    assert "finalize_solution" in action_names


# ---------------------------------------------------------------------------
# Live Ollama integration test (skipped when Ollama is not running)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not reachable at 127.0.0.1:11434")
@pytest.mark.asyncio
async def test_live_ollama_full_workflow() -> None:
    """Run the complete workflow against a real local Ollama instance."""
    loader = ConfigLoader()
    workflow = loader.load_workflow(WORKFLOW_NAME)
    model_registry = ModelRegistry()
    for provider in loader.load_models().providers:
        model_registry.register_provider_config(provider)
    graph = GraphBuilder(model_registry, ToolRegistry(), config_loader=loader).compile(workflow)

    state = initial_state(
        run_id="live-ollama-test",
        workflow_name=WORKFLOW_NAME,
        inputs={"problem": "Write a Python function to find all prime numbers up to N using the Sieve of Eratosthenes."},
    )
    result = await graph.ainvoke(state)

    assert result["errors"] == [], f"Workflow errors: {result['errors']}"
    assert result["node_outputs"]["iterative_solve"]["final_solution"]
    assert isinstance(result["node_outputs"]["iterative_solve"]["final_score"], int)
    assert result["final_report"]
