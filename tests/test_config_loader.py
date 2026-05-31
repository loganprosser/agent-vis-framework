from pathlib import Path

import pytest

from app.core.config_loader import ConfigLoader


def test_loads_example_workflow() -> None:
    loader = ConfigLoader()
    workflow = loader.load_workflow("combinatorial_test_generation")

    assert workflow.name == "combinatorial_test_generation"
    assert workflow.entrypoint == "doc_reader"
    assert [node.id for node in workflow.nodes][0] == "doc_reader"
    assert workflow.edges[-1].target == "report_generator"


def test_prompt_files_support_nested_directories(tmp_path: Path) -> None:
    loader = ConfigLoader(tmp_path)

    prompt_file = "workflows/demo/subsystems/planner/actions/review.md"
    loader.save_prompt(prompt_file, "Review the plan.")

    assert loader.list_prompts() == [prompt_file]
    assert loader.load_prompt(prompt_file) == "Review the plan."


def test_prompt_files_reject_paths_outside_prompt_directory(tmp_path: Path) -> None:
    loader = ConfigLoader(tmp_path)

    with pytest.raises(ValueError, match="escapes prompts directory"):
        loader.save_prompt("../prompts-other/not-allowed.md", "Nope.")
