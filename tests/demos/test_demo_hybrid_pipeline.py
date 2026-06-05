"""End-to-end test for examples/hybrid_pipeline."""

from __future__ import annotations

import pytest

from tests.demos.conftest import ScriptedProvider


@pytest.mark.asyncio
async def test_hybrid_pipeline_chains_react_to_burr_subsystem(build_graph, make_state) -> None:
    # Sequence (in scripted order):
    #   1. research orchestrator: ask librarian
    #   2. librarian subagent: returns a fact paragraph
    #   3. research orchestrator: emit final answer
    #   4. refine subsystem `plan` action LLM call
    #   5. refine subsystem `act` action LLM call
    provider = ScriptedProvider(
        [
            'Thought: ask librarian\nAction: librarian\nAction Input: {"message": "burr"}',
            "Apache Burr models stateful applications as graphs of typed actions.",
            'Thought: done\nAction: final_answer\nAction Input: {"answer": "Burr models stateful apps as action graphs."}',
            "plan: deepen the explanation by listing core primitives",
            "Burr decomposes execution into @action functions that read/write an immutable State.",
        ]
    )

    graph, _, _ = build_graph("demo_hybrid_pipeline", provider=provider)
    state = make_state("demo_hybrid_pipeline", {"topic": "Apache Burr"})
    final = await graph.ainvoke(state)

    research_out = final["node_outputs"]["research"]
    refine_out = final["node_outputs"]["refine"]

    assert research_out["answer"].startswith("Burr")
    # The refine subsystem received the ReAct final answer as its `task`,
    # ran plan + act, and produced two non-empty strings.
    assert refine_out["plan"]
    assert refine_out["answer"]
    # All five scripted responses were consumed.
    assert provider.responses == []
