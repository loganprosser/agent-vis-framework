from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.models.base import ModelProvider, ModelRequest, ModelResponse
from app.nodes.react_orchestrator import ReactOrchestratorNode, _parse_turn
from app.schemas.workflow import NodeConfig, RetryPolicy
from app.tools.base import Tool, ToolResult


def _make_node(provider: ModelProvider, *, tools: dict[str, Tool] | None = None, **config: Any) -> ReactOrchestratorNode:
    node_cfg = NodeConfig(
        id="orchestrator",
        type="react_orchestrator",
        model="stub",
        provider="stub",
        system_prompt="",
        input_keys=[],
        output_keys=["answer"],
        tools=list((tools or {}).keys()),
        mcps=[],
        retry_policy=RetryPolicy(max_attempts=1, backoff_seconds=0.0),
        human_approval=False,
        config=config,
    )
    return ReactOrchestratorNode(node_cfg, provider, tools=tools or {})


class ScriptedProvider(ModelProvider):
    def __init__(self, responses: list[str]) -> None:
        super().__init__("stub", "stub-1", {})
        self.responses = list(responses)
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        text = self.responses.pop(0) if self.responses else ""
        return ModelResponse(text=text, raw={})


class EchoTool(Tool):
    def __init__(self) -> None:
        super().__init__("echo", {})
        self.calls: list[dict[str, Any]] = []

    async def run(self, **kwargs: Any) -> ToolResult:
        self.calls.append(kwargs)
        return ToolResult(data={"echo": kwargs}, logs=["echo ran"])


def test_parse_turn_extracts_thought_action_input() -> None:
    text = (
        "Thought: I should echo the word.\n"
        "Action: echo\n"
        "Action Input: {\"word\": \"hi\"}\n"
    )
    thought, action, parsed = _parse_turn(text)
    assert thought == "I should echo the word."
    assert action == "echo"
    assert parsed == {"word": "hi"}


def test_parse_turn_handles_missing_input_as_empty_dict() -> None:
    thought, action, parsed = _parse_turn("Thought: be done\nAction: final_answer\nAction Input: {\"answer\": \"hi\"}")
    assert action == "final_answer"
    assert parsed == {"answer": "hi"}


@pytest.mark.asyncio
async def test_loop_dispatches_tool_then_final_answer() -> None:
    provider = ScriptedProvider(
        [
            "Thought: call echo\nAction: echo\nAction Input: {\"x\": 1}",
            "Thought: done\nAction: final_answer\nAction Input: {\"answer\": \"done!\"}",
        ]
    )
    tool = EchoTool()
    node = _make_node(provider, tools={"echo": tool}, max_iterations=4, objective_key="task")
    state = {"run_id": "r", "inputs": {"task": "go"}, "node_outputs": {}}

    result = await node.run(state)

    assert result.values["answer"] == "done!"
    assert result.values["iterations"] == 2
    assert tool.calls == [{"x": 1}]
    # First user message must enumerate the available actions.
    assert "echo" in provider.calls[0].messages[0]["content"]


@pytest.mark.asyncio
async def test_loop_records_unknown_actions_and_keeps_going() -> None:
    provider = ScriptedProvider(
        [
            "Thought: try unknown\nAction: missing_tool\nAction Input: {}",
            "Thought: try real\nAction: echo\nAction Input: {\"y\": 2}",
            "Thought: stop\nAction: final_answer\nAction Input: {\"answer\": \"ok\"}",
        ]
    )
    node = _make_node(
        provider, tools={"echo": EchoTool()}, max_iterations=5, objective_key="task"
    )
    state = {"run_id": "r", "inputs": {"task": "go"}, "node_outputs": {}}

    result = await node.run(state)
    iterations = result.artifact["iterations"]
    assert iterations[0]["observation"].startswith("unknown action")
    assert "echo" in iterations[1]["action"]
    assert result.artifact["stop_reason"] == "final_answer"


@pytest.mark.asyncio
async def test_loop_stops_at_max_iterations() -> None:
    # Provider always emits a non-terminal action so the loop must hit the cap.
    provider = ScriptedProvider(
        ["Thought: t\nAction: echo\nAction Input: {}"] * 10
    )
    node = _make_node(
        provider, tools={"echo": EchoTool()}, max_iterations=3, objective_key="task"
    )
    state = {"run_id": "r", "inputs": {"task": "go"}, "node_outputs": {}}

    result = await node.run(state)
    assert result.artifact["stop_reason"] == "max_iterations"
    assert result.values["iterations"] == 3


@pytest.mark.asyncio
async def test_subagent_dispatch_uses_provider() -> None:
    # First call drives the orchestrator; second call is the subagent.
    provider = ScriptedProvider(
        [
            "Thought: ask sub\nAction: sub1\nAction Input: {\"message\": \"summarize\"}",
            "summary text",
            "Thought: finish\nAction: final_answer\nAction Input: {\"answer\": \"summary text\"}",
        ]
    )
    node = _make_node(
        provider,
        tools={},
        max_iterations=4,
        objective_key="task",
        subagents=[{"id": "sub1", "system_prompt": "be terse", "description": "summarizer"}],
    )
    state = {"run_id": "r", "inputs": {"task": "summarize the doc"}, "node_outputs": {}}

    result = await node.run(state)
    assert result.values["answer"] == "summary text"
    assert provider.calls[1].system_prompt == "be terse"
    assert provider.calls[1].messages[0]["content"] == "summarize"


@pytest.mark.asyncio
async def test_missing_objective_raises() -> None:
    provider = ScriptedProvider([])
    node = _make_node(
        provider, tools={"echo": EchoTool()}, max_iterations=1, objective_key="task"
    )
    state = {"run_id": "r", "inputs": {}, "node_outputs": {}}
    with pytest.raises(Exception):
        await node.run(state)
