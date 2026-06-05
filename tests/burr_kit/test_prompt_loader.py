from __future__ import annotations

from pathlib import Path

from app.burr_kit.prompt_loader import PromptLoader


def test_resolution_chain(tmp_path: Path) -> None:
    workflow = tmp_path / "wf"
    preset = tmp_path / "preset"
    workflow.mkdir()
    preset.mkdir()
    (workflow / "agent_a.md").write_text("workflow A")
    (preset / "agent_a.md").write_text("preset A")
    (workflow / "agent_b.md").write_text("workflow B")

    loader = PromptLoader(workflow_dir=workflow, preset_dir=preset)
    assert loader.load_prompt("agent_a", "default") == "preset A"
    assert loader.load_prompt("agent_b", "default") == "workflow B"
    assert loader.load_prompt("agent_c", "default") == "default"

    assert loader.prompt_source("agent_a") == "preset"
    assert loader.prompt_source("agent_b") == "workflow"
    assert loader.prompt_source("agent_c") is None


def test_save_prompt_round_trips(tmp_path: Path) -> None:
    workflow = tmp_path / "wf"
    workflow.mkdir()
    loader = PromptLoader(workflow_dir=workflow)
    loader.save_prompt("agent_a", "hello\n")
    assert (workflow / "agent_a.md").read_text() == "hello\n"


def test_list_prompts_de_dupes_across_workflow_dirs(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x.md").write_text("a")
    (b / "x.md").write_text("b")
    (b / "y.md").write_text("b")

    loader = PromptLoader(workflow_dir=[a, b])
    assert loader.list_prompts() == {"workflow": ["x", "y"], "preset": []}
