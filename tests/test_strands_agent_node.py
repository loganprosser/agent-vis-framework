from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from app.models.base import ModelProvider, ModelRequest, ModelResponse
from app.nodes.strands_agent import StrandsAgentNode
from app.schemas.workflow import NodeConfig, RetryPolicy


class StubProvider(ModelProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover
        return ModelResponse(text="")


class _FakeResult:
    def __init__(self, text: str, tool_uses: list[dict[str, Any]] | None = None) -> None:
        self.message = {"role": "assistant", "content": [{"text": text}]}
        self.tool_uses = tool_uses or []


class _FakeAgent:
    """Mirrors enough of the Strands Agent surface for tests."""

    def __init__(self, *, system_prompt: str = "", **kwargs: Any) -> None:
        self.system_prompt = system_prompt
        self.kwargs = kwargs
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> _FakeResult:
        self.calls.append(prompt)
        return _FakeResult(
            text=f"answer for: {prompt}",
            tool_uses=[{"name": "search", "input": {"q": prompt}, "output": "ok"}],
        )


def _install_fake_module(monkeypatch, build_kwargs_capture: dict[str, Any]) -> None:
    mod = types.ModuleType("test_fake_strands_factory")

    def build(*, prompt: str | None = None, model_provider: Any = None) -> _FakeAgent:
        build_kwargs_capture["prompt"] = prompt
        build_kwargs_capture["model_provider"] = model_provider
        return _FakeAgent(system_prompt="be brief")

    mod.build = build  # type: ignore[attr-defined]
    sys.modules["test_fake_strands_factory"] = mod
    monkeypatch.setattr(
        sys,
        "modules",
        {**sys.modules, "test_fake_strands_factory": mod},
    )


def _make_node(**config: Any) -> StrandsAgentNode:
    return StrandsAgentNode(
        NodeConfig(
            id="strands",
            type="strands_agent",
            model="stub",
            provider="stub",
            system_prompt="",
            input_keys=[],
            output_keys=["answer"],
            tools=[],
            mcps=[],
            retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
            human_approval=False,
            config=config,
        ),
        StubProvider("stub", "stub-1", {}),
    )


@pytest.mark.asyncio
async def test_invokes_factory_and_extracts_answer(monkeypatch) -> None:
    capture: dict[str, Any] = {}
    _install_fake_module(monkeypatch, capture)
    node = _make_node(
        agent_module="test_fake_strands_factory",
        agent_factory="build",
        prompt_key="prompt",
        input_map={"prompt": "inputs.prompt"},
        output_map={"answer": "answer"},
    )
    state = {"run_id": "r", "inputs": {"prompt": "tell me about RITS"}, "node_outputs": {}}

    result = await node.run(state)

    assert result.values["answer"] == "answer for: tell me about RITS"
    assert capture["model_provider"] is node.model_provider
    assert result.artifact["tool_calls"][0]["name"] == "search"
    assert result.artifact["messages"][0]["content"].startswith("answer for")


@pytest.mark.asyncio
async def test_missing_module_or_factory_raises(monkeypatch) -> None:
    node = _make_node(agent_factory="build", prompt_key="prompt")
    state = {"run_id": "r", "inputs": {"prompt": "hi"}, "node_outputs": {}}
    with pytest.raises(Exception):
        await node.run(state)


@pytest.mark.asyncio
async def test_missing_prompt_raises(monkeypatch) -> None:
    capture: dict[str, Any] = {}
    _install_fake_module(monkeypatch, capture)
    node = _make_node(
        agent_module="test_fake_strands_factory",
        agent_factory="build",
        prompt_key="prompt",
        input_map={"prompt": "inputs.prompt"},
    )
    state = {"run_id": "r", "inputs": {}, "node_outputs": {}}
    with pytest.raises(Exception):
        await node.run(state)


@pytest.mark.asyncio
async def test_output_map_can_project_arbitrary_artifact_field(monkeypatch) -> None:
    capture: dict[str, Any] = {}
    _install_fake_module(monkeypatch, capture)
    node = _make_node(
        agent_module="test_fake_strands_factory",
        agent_factory="build",
        prompt_key="prompt",
        input_map={"prompt": "inputs.prompt"},
        output_map={"echoed_prompt": "artifact.prompt", "answer": "answer"},
    )
    state = {"run_id": "r", "inputs": {"prompt": "x"}, "node_outputs": {}}
    result = await node.run(state)
    assert result.values["echoed_prompt"] == "x"
    assert result.values["answer"].endswith("x")
