from __future__ import annotations

from pathlib import Path

import pytest

from app.burr_kit.presets import (
    PresetConfig,
    list_presets,
    list_presets_for_workflow,
    load_preset,
    load_preset_prompts,
)


@pytest.fixture()
def presets_root(tmp_path: Path) -> Path:
    root = tmp_path / "presets"
    (root / "strict").mkdir(parents=True)
    (root / "strict" / "preset.yaml").write_text(
        "description: strict\nworkflows: [demo]\nconfig: {style: terse}\n"
    )
    (root / "strict" / "plan.md").write_text("be terse")
    (root / "loose").mkdir()
    (root / "loose" / "preset.yaml").write_text("description: any\n")
    (root / "broken").mkdir()
    (root / "broken" / "preset.yaml").write_text("workflows: not-a-list\n")
    return root


def test_list_presets_returns_only_well_formed_dirs(presets_root: Path) -> None:
    assert list_presets(presets_root) == ["broken", "loose", "strict"]


def test_list_presets_for_workflow_filters_by_scope(presets_root: Path) -> None:
    # `broken` raises on load → silently dropped.
    assert list_presets_for_workflow(presets_root, "demo") == ["loose", "strict"]
    assert list_presets_for_workflow(presets_root, "other") == ["loose"]


def test_load_preset_round_trips_config(presets_root: Path) -> None:
    preset = load_preset(presets_root, "strict")
    assert isinstance(preset, PresetConfig)
    assert preset.config == {"style": "terse"}
    assert preset.applies_to("demo")
    assert not preset.applies_to("other")


def test_load_preset_prompts_picks_up_md_files(presets_root: Path) -> None:
    prompts = load_preset_prompts(presets_root, "strict")
    assert prompts == {"plan": "be terse"}


def test_load_preset_missing_raises(presets_root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_preset(presets_root, "nope")
