"""Shared test plumbing for the examples/ demos.

These fixtures let each demo test run its workflow YAML through the real
GraphBuilder pipeline (so the wiring is exercised end-to-end), but with a
provider whose ``generate`` method returns scripted responses so the
demos run deterministically without a live LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state
from app.models.base import ModelProvider, ModelRequest, ModelResponse
from app.schemas.workflow import ModelProviderConfig


class ScriptedProvider(ModelProvider):
    """Returns successive entries from a scripted response list.

    If ``responses`` is empty, every call returns a deterministic stub so
    long-running loops eventually terminate cleanly instead of hanging.
    """

    def __init__(self, responses: list[str] | None = None, fallback: str = "Thought: stop\nAction: final_answer\nAction Input: {\"answer\": \"\"}") -> None:
        super().__init__("scripted", "scripted-1", {})
        self.responses = list(responses or [])
        self.fallback = fallback
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if self.responses:
            text = self.responses.pop(0)
        else:
            text = self.fallback
        return ModelResponse(text=text, raw={"scripted": True})


@pytest.fixture()
def configs_dir() -> Path:
    return Path("configs")


@pytest.fixture()
def build_graph() -> Callable[..., Any]:
    """Factory: ``build_graph(workflow_name, *, provider, configs_dir=None)``."""

    def _factory(
        workflow_name: str,
        *,
        provider: ModelProvider,
        configs_dir: Path | None = None,
    ):
        loader = ConfigLoader(config_dir=configs_dir or Path("configs"))
        workflow = loader.load_workflow(workflow_name)

        registry = ModelRegistry()
        for cfg in loader.load_models().providers:
            registry.register_provider_config(cfg)
        # Pin the scripted provider under every provider id the workflow refers to.
        for node in workflow.nodes:
            if node.provider:
                registry._providers[node.provider] = provider  # noqa: SLF001
        # Also register an explicit "scripted" id for callers that want it.
        registry.register_provider_config(
            ModelProviderConfig.model_validate(
                {
                    "id": "scripted",
                    "type": "mock",
                    "default_model": "scripted-1",
                    "config": {},
                }
            )
        )
        registry._providers["scripted"] = provider  # noqa: SLF001

        mcps = {s.id: s for s in loader.load_mcps().servers}
        tools = ToolRegistry(mcps)
        for cfg in loader.load_tools().tools:
            tools.register_tool_config(cfg)
        graph = GraphBuilder(registry, tools, config_loader=loader).compile(workflow)
        return graph, loader, workflow

    return _factory


@pytest.fixture()
def make_state() -> Callable[..., dict[str, Any]]:
    def _factory(workflow_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        return initial_state(
            run_id=f"test-{workflow_name}",
            workflow_name=workflow_name,
            inputs=inputs,
        )

    return _factory
