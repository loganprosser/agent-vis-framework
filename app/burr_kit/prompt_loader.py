"""Prompt loading with markdown file support and chained directory search.

Search order (first hit wins):
  1. preset_dir/<agent>.md   (if a preset is active)
  2. workflow_dir/<agent>.md (one or more workflow-scoped dirs)
  3. default_prompt          (hardcoded fallback)

Ported, with light cleanup, from
``burr-combinatorial-testing/src/atf/llm/prompt_loader.py``.
"""

from __future__ import annotations

from pathlib import Path


class PromptLoader:
    """Resolve agent system prompts from markdown files with fallbacks."""

    def __init__(
        self,
        workflow_dir: Path | str | list[Path | str] | tuple[Path | str, ...] | None = None,
        preset_dir: Path | str | None = None,
    ) -> None:
        if isinstance(workflow_dir, (list, tuple)):
            self.workflow_dirs = [Path(p) for p in workflow_dir]
        elif workflow_dir:
            self.workflow_dirs = [Path(workflow_dir)]
        else:
            self.workflow_dirs = []
        self.workflow_dir = self.workflow_dirs[0] if self.workflow_dirs else None
        self.preset_dir = Path(preset_dir) if preset_dir else None

    def load_prompt(self, agent_name: str, default_prompt: str) -> str:
        if self.preset_dir is not None:
            path = self.preset_dir / f"{agent_name}.md"
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8").strip()
                except (OSError, UnicodeDecodeError):
                    pass

        for workflow_dir in self.workflow_dirs:
            path = workflow_dir / f"{agent_name}.md"
            if path.exists():
                try:
                    return path.read_text(encoding="utf-8").strip()
                except (OSError, UnicodeDecodeError):
                    pass

        return default_prompt

    def save_prompt(self, agent_name: str, content: str, *, target: str = "workflow") -> Path:
        if target == "preset" and self.preset_dir is not None:
            dest_dir = self.preset_dir
        elif self.workflow_dir is not None:
            dest_dir = self.workflow_dir
        else:
            raise ValueError("No prompt directory configured for writing")
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{agent_name}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def list_prompts(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {"workflow": [], "preset": []}
        workflow_names: set[str] = set()
        for workflow_dir in self.workflow_dirs:
            if workflow_dir.exists():
                workflow_names.update(p.stem for p in workflow_dir.glob("*.md"))
        result["workflow"] = sorted(workflow_names)
        if self.preset_dir and self.preset_dir.exists():
            result["preset"] = sorted(p.stem for p in self.preset_dir.glob("*.md"))
        return result

    def prompt_source(self, agent_name: str) -> str | None:
        if self.preset_dir is not None and (self.preset_dir / f"{agent_name}.md").exists():
            return "preset"
        for workflow_dir in self.workflow_dirs:
            if (workflow_dir / f"{agent_name}.md").exists():
                return "workflow"
        return None
