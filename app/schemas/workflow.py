from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1)
    backoff_seconds: float = Field(default=0.0, ge=0.0)


class BurrActionConfig(BaseModel):
    id: str = Field(min_length=1)
    label: str = ""
    kind: Literal["agent", "action", "router", "tool", "human"] = "action"
    description: str = ""
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    model: str | None = None
    prompt: str = ""
    prompt_file: str | None = None

    model_config = ConfigDict(extra="forbid")


class BurrTransitionConfig(BaseModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    condition: str = "default"

    model_config = ConfigDict(extra="forbid")


class BurrTopologyConfig(BaseModel):
    entrypoint: str = Field(min_length=1)
    actions: list[BurrActionConfig] = Field(default_factory=list)
    transitions: list[BurrTransitionConfig] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_graph_references(self) -> "BurrTopologyConfig":
        action_ids = {action.id for action in self.actions}
        if len(action_ids) != len(self.actions):
            raise ValueError("Burr topology action ids must be unique.")
        if self.entrypoint not in action_ids:
            raise ValueError(f"Burr topology entrypoint '{self.entrypoint}' is not a defined action.")
        for transition in self.transitions:
            if transition.source not in action_ids:
                raise ValueError(
                    f"Burr topology transition source '{transition.source}' is not a defined action."
                )
            if transition.target not in action_ids:
                raise ValueError(
                    f"Burr topology transition target '{transition.target}' is not a defined action."
                )
        return self


class BurrSubsystemConfig(BaseModel):
    app_module: str = Field(min_length=1)
    app_factory: str = Field(min_length=1)
    input_map: dict[str, str] = Field(default_factory=dict)
    output_map: dict[str, str] = Field(default_factory=dict)
    halt_after: list[str] | None = None
    terminal_states: list[str] | None = None
    artifact_name: str = Field(default="burr_final_state", min_length=1)
    timeout_seconds: float | None = Field(default=None, gt=0)
    fail_on_error: bool = True
    topology: BurrTopologyConfig | None = None
    ui: dict[str, Any] | None = None
    # burr_kit integration: optional preset bundle + prompt directory the
    # factory can consume via injected ``preset`` / ``prompt_loader`` / ``agent_runner``
    # kwargs. ``presets_root`` and ``prompt_dir`` are resolved relative to
    # ``${WORKFLOW_CONFIG_DIR}`` (default ``configs/``) when relative.
    preset: str | None = None
    presets_root: str | None = None
    prompt_dir: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("halt_after", "terminal_states", mode="before")
    @classmethod
    def normalize_string_list(cls, value):
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("halt_after", "terminal_states")
    @classmethod
    def validate_string_list(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (not value or any(not item for item in value)):
            raise ValueError("must contain at least one non-empty string")
        return value

    @field_validator("input_map", "output_map")
    @classmethod
    def validate_mapping_paths(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not key or not path for key, path in value.items()):
            raise ValueError("keys and paths must be non-empty strings")
        return value

    @model_validator(mode="after")
    def validate_halt_condition(self) -> "BurrSubsystemConfig":
        if bool(self.halt_after) == bool(self.terminal_states):
            raise ValueError("set exactly one of halt_after or terminal_states")
        return self


class NodeConfig(BaseModel):
    id: str
    type: str
    model: str | None = None
    provider: str | None = None
    system_prompt: str = ""
    system_prompt_file: str | None = None
    input_keys: list[str] = Field(default_factory=list)
    output_keys: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    mcps: list[str] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    human_approval: bool = False
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_typed_config(self) -> "NodeConfig":
        if self.type == "burr_subsystem":
            self.config = BurrSubsystemConfig.model_validate(self.config).model_dump(exclude_none=True)
        return self


class EdgeConfig(BaseModel):
    source: str
    target: str
    label: str | None = None

    model_config = ConfigDict(extra="forbid")


class WorkflowConfig(BaseModel):
    name: str
    version: str = "0.1.0"
    description: str = ""
    entrypoint: str
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_graph_references(self) -> "WorkflowConfig":
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("Workflow node ids must be unique.")
        if self.entrypoint not in node_ids:
            raise ValueError(f"Entrypoint '{self.entrypoint}' is not a defined node.")
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"Edge source '{edge.source}' is not a defined node.")
            if edge.target not in node_ids:
                raise ValueError(f"Edge target '{edge.target}' is not a defined node.")
        return self


class ModelProviderConfig(BaseModel):
    id: str
    type: Literal["mock", "openai", "anthropic", "ibm", "rits", "litellm", "local", "ollama"]
    default_model: str
    config: dict[str, Any] = Field(default_factory=dict)


class ToolConfig(BaseModel):
    id: str
    type: Literal["shell", "tnt_cli", "mcp", "test_runner", "repo_reader"]
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    id: str
    name: str
    transport: Literal["stdio"] = "stdio"
    enabled: bool = True
    command: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=10.0, gt=0)


class ModelsConfig(BaseModel):
    providers: list[ModelProviderConfig] = Field(default_factory=list)


class ToolsConfig(BaseModel):
    tools: list[ToolConfig] = Field(default_factory=list)


class McpsConfig(BaseModel):
    servers: list[McpServerConfig] = Field(default_factory=list)
