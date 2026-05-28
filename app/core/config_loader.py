from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from app.schemas.workflow import ModelsConfig, ToolsConfig, WorkflowConfig

T = TypeVar("T", bound=BaseModel)


class ConfigLoader:
    def __init__(self, config_dir: Path | str = "configs") -> None:
        self.config_dir = Path(config_dir)
        self.workflow_dir = self.config_dir / "workflows"

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
            yaml.safe_dump(workflow.model_dump(mode="json"), config_file, sort_keys=False)
        return workflow

    def load_models(self) -> ModelsConfig:
        return self._load_yaml_model(self.config_dir / "models.yaml", ModelsConfig)

    def load_tools(self) -> ToolsConfig:
        return self._load_yaml_model(self.config_dir / "tools.yaml", ToolsConfig)

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
