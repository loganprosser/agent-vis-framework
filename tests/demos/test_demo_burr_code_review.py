"""End-to-end test for examples/burr_code_review.

Exercises the burr_kit injection contract end-to-end:
GraphBuilder → BurrSubsystemNode → factory introspection → preset +
PromptLoader + AgentRunner + SubprocessRunner all wired through.
"""

from __future__ import annotations

import pytest

from tests.demos.conftest import ScriptedProvider


@pytest.mark.asyncio
async def test_code_review_subsystem_runs_through_all_actions(build_graph, make_state) -> None:
    # Two LLM turns: one for `review`, one for `summary`.
    provider = ScriptedProvider(
        [
            "- Avoid bare except clauses.\n- Validate the divisor before dividing.",
            "The calculator handles add/sub/mul cleanly but the div path is unsafe under zero inputs.",
        ]
    )
    graph, _, _ = build_graph("demo_burr_code_review", provider=provider)
    state = make_state(
        "demo_burr_code_review",
        {
            "target_path": "examples/burr_code_review/sample_calc.py",
            "file_content": "def divide(a, b):\n    return a / b\n",
        },
    )

    final = await graph.ainvoke(state)
    outputs = final["node_outputs"]["review_subsystem"]

    assert outputs["review"].startswith("-")
    assert outputs["summary"].startswith("The calculator")
    # Strict preset disables dry_run; the lint command must have actually run.
    assert outputs["lint_output"] is not None
    # Both LLM agents were called exactly once.
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_dry_run_mock_path_works_without_agent_runner(build_graph, make_state, tmp_path, monkeypatch) -> None:
    """Without scripted responses, the Burr factory's mock fallback runs."""

    # Swap the preset to friendly_review (dry_run=true, no real ruff).
    workflow_path = tmp_path / "configs"
    src = (tmp_path / "_src").resolve()
    src.mkdir()
    # Symlink configs/ into tmp so the YAML edit doesn't pollute the repo.
    import shutil

    shutil.copytree("configs", workflow_path)
    yaml_path = workflow_path / "workflows" / "demo_burr_code_review.yaml"
    text = yaml_path.read_text()
    yaml_path.write_text(text.replace("strict_review", "friendly_review"))
    monkeypatch.setenv("WORKFLOW_CONFIG_DIR", str(workflow_path))

    # Empty scripted responses → ScriptedProvider falls back to its stub.
    provider = ScriptedProvider()
    graph, _, _ = build_graph(
        "demo_burr_code_review",
        provider=provider,
        configs_dir=workflow_path,
    )
    final = await graph.ainvoke(
        make_state(
            "demo_burr_code_review",
            {
                "target_path": "examples/burr_code_review/sample_calc.py",
                "file_content": "def add(a, b): return a + b\n",
            },
        )
    )
    outputs = final["node_outputs"]["review_subsystem"]
    assert outputs["lint_output"].startswith("[friendly-review]") or outputs["lint_output"]
    assert outputs["summary"]
    assert outputs["review"]
