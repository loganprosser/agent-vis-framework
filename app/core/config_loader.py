from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from app.schemas.workflow import McpsConfig, ModelsConfig, NodeConfig, ToolsConfig, WorkflowConfig

T = TypeVar("T", bound=BaseModel)


class ConfigLoader:
    def __init__(self, config_dir: Path | str | None = None) -> None:
        self.config_dir = Path(config_dir or os.getenv("WORKFLOW_CONFIG_DIR", "configs"))
        self.workflow_dir = self.config_dir / "workflows"

    @property
    def prompts_dir(self) -> Path:
        return self.config_dir / "prompts"

    def list_workflows(self) -> list[str]:
        if not self.workflow_dir.exists():
            return []
        return sorted(path.stem for path in self.workflow_dir.glob("*.yaml"))

    def load_workflow(self, workflow_name: str) -> WorkflowConfig:
        return self._load_yaml_model(
            self._workflow_path(workflow_name),
            WorkflowConfig,
        )

    def save_workflow(self, workflow_name: str, workflow: WorkflowConfig) -> WorkflowConfig:
        if workflow.name != workflow_name:
            raise ValueError("Workflow name must match the save path.")
        path = self._workflow_path(workflow_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as config_file:
            yaml.safe_dump(workflow.model_dump(mode="json", exclude_none=True), config_file, sort_keys=False)
        return workflow

    def load_models(self) -> ModelsConfig:
        return self._load_yaml_model(self.config_dir / "models.yaml", ModelsConfig)

    def load_tools(self) -> ToolsConfig:
        return self._load_yaml_model(self.config_dir / "tools.yaml", ToolsConfig)

    def load_mcps(self) -> McpsConfig:
        path = self.config_dir / "mcps.yaml"
        if not path.exists():
            return McpsConfig()
        return self._load_yaml_model(path, McpsConfig)

    # --- Prompt file methods ---

    def list_prompts(self) -> list[str]:
        if not self.prompts_dir.exists():
            return []
        return sorted(str(p.relative_to(self.prompts_dir)) for p in self.prompts_dir.rglob("*.md"))

    def load_prompt(self, prompt_file: str) -> str:
        path = self._resolve_prompt_path(prompt_file)
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        return path.read_text(encoding="utf-8")

    def save_prompt(self, prompt_file: str, content: str) -> str:
        path = self._resolve_prompt_path(prompt_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return prompt_file

    def delete_prompt(self, prompt_file: str) -> None:
        path = self._resolve_prompt_path(prompt_file)
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        path.unlink()

    def resolve_system_prompt(self, node_config: NodeConfig) -> str:
        if node_config.system_prompt_file:
            path = self._resolve_prompt_path(node_config.system_prompt_file)
            if path.exists():
                return path.read_text(encoding="utf-8")
            if node_config.system_prompt:
                return node_config.system_prompt
            raise FileNotFoundError(
                f"Prompt file not found: {node_config.system_prompt_file} (resolved to {path})"
            )
        return node_config.system_prompt

    def _resolve_prompt_path(self, prompt_file: str) -> Path:
        resolved = (self.prompts_dir / prompt_file).resolve()
        if not str(resolved).startswith(str(self.prompts_dir.resolve())):
            raise ValueError(f"Prompt file path escapes prompts directory: {prompt_file}")
        return resolved

    # --- Internal helpers ---

    def _load_yaml_model(self, path: Path, model_type: type[T]) -> T:
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with path.open("r", encoding="utf-8") as config_file:
            raw: Any = yaml.safe_load(config_file) or {}
        return model_type.model_validate(raw)

    def _workflow_path(self, workflow_name: str) -> Path:
        if not workflow_name.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Workflow names may only contain letters, numbers, underscores, and hyphens.")
        return self.workflow_dir / f"{workflow_name}.yaml"
