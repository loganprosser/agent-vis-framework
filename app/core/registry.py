from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.models.anthropic_provider import AnthropicModelProvider
from app.models.base import ModelProvider
from app.models.mock_provider import MockModelProvider
from app.models.openai_provider import OpenAIModelProvider
from app.schemas.workflow import McpServerConfig, ModelProviderConfig, ToolConfig
from app.tools.base import Tool
from app.tools.mcp_tool import McpTool
from app.tools.shell_tool import ShellTool
from app.tools.tnt_cli_tool import TntCliTool


ModelFactory = Callable[[ModelProviderConfig], ModelProvider]
ToolFactory = Callable[[ToolConfig], Tool]
NodeFactory = Callable[..., Any]


class ModelRegistry:
    def __init__(self) -> None:
        self._provider_type_factories: dict[str, ModelFactory] = {
            "mock": lambda config: MockModelProvider(config.id, config.default_model, config.config),
            "openai": lambda config: OpenAIModelProvider(config.id, config.default_model, config.config),
            "anthropic": lambda config: AnthropicModelProvider(config.id, config.default_model, config.config),
            "ibm": lambda config: OpenAIModelProvider(config.id, config.default_model, config.config),
            "litellm": lambda config: OpenAIModelProvider(config.id, config.default_model, config.config),
            "local": lambda config: MockModelProvider(config.id, config.default_model, config.config),
        }
        self._providers: dict[str, ModelProvider] = {}

    def register_provider_config(self, config: ModelProviderConfig) -> None:
        try:
            factory = self._provider_type_factories[config.type]
        except KeyError as exc:
            raise ValueError(f"Unknown model provider type: {config.type}") from exc
        self._providers[config.id] = factory(config)

    def get(self, provider_id: str | None) -> ModelProvider:
        if provider_id and provider_id in self._providers:
            return self._providers[provider_id]
        if "mock" in self._providers:
            return self._providers["mock"]
        if self._providers:
            return next(iter(self._providers.values()))
        raise ValueError("No model providers are registered.")


class ToolRegistry:
    def __init__(self, mcp_servers: dict[str, McpServerConfig] | None = None) -> None:
        self._mcp_servers = mcp_servers or {}
        self._tool_type_factories: dict[str, ToolFactory] = {
            "shell": lambda config: ShellTool(config.id, {"enabled": config.enabled, **config.config}),
            "tnt_cli": lambda config: TntCliTool(config.id, config.config),
            "mcp": self._create_mcp_tool,
            "test_runner": lambda config: ShellTool(config.id, {"enabled": config.enabled, **config.config}),
            "repo_reader": self._create_mcp_tool,
        }
        self._tools: dict[str, Tool] = {}

    def register_tool_config(self, config: ToolConfig) -> None:
        try:
            factory = self._tool_type_factories[config.type]
        except KeyError as exc:
            raise ValueError(f"Unknown tool type: {config.type}") from exc
        self._tools[config.id] = factory(config)

    def get(self, tool_id: str) -> Tool:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise ValueError(f"Tool is not registered: {tool_id}") from exc

    def many(self, tool_ids: list[str]) -> dict[str, Tool]:
        return {tool_id: self.get(tool_id) for tool_id in tool_ids}

    def _create_mcp_tool(self, config: ToolConfig) -> McpTool:
        server_id = str(config.config.get("server_id") or config.config.get("server_name") or "")
        server = self._mcp_servers.get(server_id)
        return McpTool(config.id, {"enabled": config.enabled, **config.config}, server)


class NodeRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, NodeFactory] = {}

    def register(self, node_type: str, factory: NodeFactory) -> None:
        self._factories[node_type] = factory

    def create(self, node_type: str, **kwargs: Any) -> Any:
        try:
            factory = self._factories[node_type]
        except KeyError as exc:
            raise ValueError(f"Unknown node type: {node_type}") from exc
        return factory(**kwargs)
