from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=1, ge=1)
    backoff_seconds: float = Field(default=0.0, ge=0.0)


class NodeConfig(BaseModel):
    id: str
    type: str
    model: str | None = None
    provider: str | None = None
    system_prompt: str = ""
    input_keys: list[str] = Field(default_factory=list)
    output_keys: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    mcps: list[str] = Field(default_factory=list)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    human_approval: bool = False
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


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
    type: Literal["mock", "openai", "anthropic", "ibm", "local"]
    default_model: str
    config: dict[str, Any] = Field(default_factory=dict)


class ToolConfig(BaseModel):
    id: str
    type: Literal["shell", "tnt_cli", "mcp", "test_runner", "repo_reader"]
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class ModelsConfig(BaseModel):
    providers: list[ModelProviderConfig] = Field(default_factory=list)


class ToolsConfig(BaseModel):
    tools: list[ToolConfig] = Field(default_factory=list)
