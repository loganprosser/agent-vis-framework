"""File-backed preset bundles for Burr subsystems.

A preset lives under ``<presets_root>/<name>/``:

    <name>/
      preset.yaml      — required
      <agent>.md       — optional per-agent prompt overrides

The ``preset.yaml`` schema is framework-agnostic. ATF-specific fields
(``parameter_overrides``, ``agents: AgentFlags``) intentionally do not exist
here; if a downstream Burr subsystem needs them, it can read them out of the
generic ``overrides`` list or ``config`` dict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PresetConfig(BaseModel):
    """A tuning bundle applied on top of a Burr factory.

    Fields:
        description: free-form human description.
        workflows: scope. Empty means "applies to any workflow".
        config: arbitrary key/value bag merged into the factory's config.
        overrides: list of arbitrary records (constraints, parameter tweaks,
                   transition gates, ...). Interpretation is up to the
                   subsystem; the kit only round-trips them.
    """

    description: str = ""
    workflows: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    overrides: list[dict[str, Any]] = Field(default_factory=list)

    def applies_to(self, workflow: str) -> bool:
        return not self.workflows or workflow in self.workflows


def list_presets(presets_root: Path | str) -> list[str]:
    """Return preset names that have a ``preset.yaml`` file."""
    root = Path(presets_root)
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir() if d.is_dir() and (d / "preset.yaml").exists()
    )


def list_presets_for_workflow(presets_root: Path | str, workflow: str) -> list[str]:
    """Filter ``list_presets`` to entries whose preset applies to *workflow*."""
    out: list[str] = []
    for name in list_presets(presets_root):
        try:
            preset = load_preset(presets_root, name)
        except Exception:
            continue
        if preset.applies_to(workflow):
            out.append(name)
    return out


def load_preset(presets_root: Path | str, name: str) -> PresetConfig:
    path = Path(presets_root) / name / "preset.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Preset '{name}' not found at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return PresetConfig.model_validate(data)


def load_preset_prompts(presets_root: Path | str, name: str) -> dict[str, str]:
    """Return ``{agent_name: prompt_text}`` for every ``<agent>.md`` in the preset."""
    preset_dir = Path(presets_root) / name
    if not preset_dir.is_dir():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in preset_dir.glob("*.md")}
