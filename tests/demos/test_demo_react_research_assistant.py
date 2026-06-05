"""End-to-end test for examples/research_assistant."""

from __future__ import annotations

import json

import pytest

from tests.demos.conftest import ScriptedProvider


@pytest.mark.asyncio
async def test_react_research_assistant_completes_with_final_answer(build_graph, make_state) -> None:
    # Scripted ReAct trace: outline (subagent) → mcp echo → summary → final
    provider = ScriptedProvider(
        [
            'Thought: outline first\nAction: outliner\nAction Input: {"message": "history of RITS"}',
            "- Read the RITS overview\n- Check available endpoints\n- Confirm GLM-5.1-FP8 availability",
            'Thought: confirm with mcp\nAction: builtin_demo_mcp.echo\nAction Input: {"text": "hi from echo"}',
            'Thought: summarise the outline\nAction: summarizer\nAction Input: {"message": "the three outline bullets"}',
            "RITS hosts IBM-internal LLM endpoints behind a LiteLLM-compatible proxy.",
            'Thought: done\nAction: final_answer\nAction Input: {"answer": "RITS is IBM\'s internal model gateway."}',
        ]
    )

    graph, _, _ = build_graph("demo_react_research_assistant", provider=provider)
    state = make_state("demo_react_research_assistant", {"objective": "Explain RITS in two sentences"})
    final = await graph.ainvoke(state)

    outputs = final["node_outputs"]["orchestrate"]
    artifact = final["artifacts"]["orchestrate"]

    assert outputs["answer"].startswith("RITS")
    assert artifact["stop_reason"] == "final_answer"
    assert outputs["iterations"] == 4  # outliner, echo, summarizer, final
    # Catalog must contain declared tool, both subagents, and MCP-discovered tools
    names = {entry["name"]: entry["kind"] for entry in artifact["catalog"]}
    assert names["builtin_demo_mcp"] == "tool"
    assert names["outliner"] == "subagent"
    assert names["summarizer"] == "subagent"
    assert "builtin_demo_mcp.echo" in names and names["builtin_demo_mcp.echo"] == "mcp"


@pytest.mark.asyncio
async def test_react_loop_terminates_on_max_iterations_with_no_final(build_graph, make_state) -> None:
    # Provider always emits a non-terminal turn — the loop must hit max_iterations cleanly.
    provider = ScriptedProvider(fallback='Thought: t\nAction: outliner\nAction Input: {"message": "x"}')
    graph, _, _ = build_graph("demo_react_research_assistant", provider=provider)
    state = make_state("demo_react_research_assistant", {"objective": "X"})
    final = await graph.ainvoke(state)

    artifact = final["artifacts"]["orchestrate"]
    assert artifact["stop_reason"] == "max_iterations"
    # max_iterations is 6 in the demo YAML.
    assert artifact["iterations"] and len(artifact["iterations"]) == 6


@pytest.mark.asyncio
async def test_unknown_action_does_not_break_loop(build_graph, make_state) -> None:
    provider = ScriptedProvider(
        [
            'Thought: typo\nAction: notathing\nAction Input: {}',
            'Thought: ok\nAction: final_answer\nAction Input: {"answer": "recovered"}',
        ]
    )
    graph, _, _ = build_graph("demo_react_research_assistant", provider=provider)
    final = await graph.ainvoke(make_state("demo_react_research_assistant", {"objective": "X"}))
    artifact = final["artifacts"]["orchestrate"]
    assert artifact["iterations"][0]["observation"].startswith("unknown action")
    assert artifact["final_answer"] == "recovered"
