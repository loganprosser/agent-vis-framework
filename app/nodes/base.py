from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from app.core.state import WorkflowState
from app.models.base import ModelProvider, ModelRequest
from app.schemas.workflow import NodeConfig
from app.tools.base import Tool


class BaseNode(ABC):
    def __init__(
        self,
        config: NodeConfig,
        model_provider: ModelProvider,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        self.config = config
        self.model_provider = model_provider
        self.tools = tools or {}

    async def __call__(self, state: WorkflowState) -> WorkflowState:
        logs = list(state.get("logs", []))
        errors = list(state.get("errors", []))
        approvals = dict(state.get("approvals", {}))

        if self.config.human_approval:
            approvals[self.config.id] = {
                "required": True,
                "status": "auto_approved_for_mock_run",
            }

        for attempt in range(1, self.config.retry_policy.max_attempts + 1):
            try:
                output = await self.run(state)
                return self._merge_success(state, output, logs, approvals)
            except Exception as exc:  # noqa: BLE001 - capture node errors into workflow state.
                logs.append(f"{self.config.id}: attempt {attempt} failed: {exc}")
                if attempt >= self.config.retry_policy.max_attempts:
                    errors.append({"node_id": self.config.id, "message": str(exc)})
                    return self._merge_error(state, logs, errors, approvals)
                if self.config.retry_policy.backoff_seconds:
                    await asyncio.sleep(self.config.retry_policy.backoff_seconds)

        return self._merge_error(state, logs, errors, approvals)

    @abstractmethod
    async def run(self, state: WorkflowState) -> dict[str, Any]:
        """Return this node's output payload."""

    def context(self, state: WorkflowState) -> dict[str, Any]:
        node_outputs = state.get("node_outputs", {})
        context: dict[str, Any] = {
            "inputs": state.get("inputs", {}),
            "artifacts": state.get("artifacts", {}),
            "node_outputs": node_outputs,
        }
        for key in self.config.input_keys:
            if key in state.get("inputs", {}):
                context[key] = state["inputs"][key]
            if key in node_outputs:
                context[key] = node_outputs[key]
        return context

    async def ask_model(self, state: WorkflowState, user_message: str) -> str:
        response = await self.model_provider.generate(
            ModelRequest(
                model=self.config.model or self.model_provider.default_model,
                system_prompt=self.config.system_prompt,
                messages=[{"role": "user", "content": user_message}],
                context=self.context(state),
            )
        )
        return response.text

    def _merge_success(
        self,
        state: WorkflowState,
        output: dict[str, Any],
        logs: list[str],
        approvals: dict[str, Any],
    ) -> WorkflowState:
        node_outputs = dict(state.get("node_outputs", {}))
        artifacts = dict(state.get("artifacts", {}))
        node_outputs[self.config.id] = output
        artifacts[self.config.id] = output
        logs.append(f"{self.config.id}: completed")

        next_state: WorkflowState = dict(state)
        next_state.update(
            {
                "node_outputs": node_outputs,
                "artifacts": artifacts,
                "logs": logs,
                "approvals": approvals,
            }
        )
        if "final_report" in output:
            next_state["final_report"] = output["final_report"]
        return next_state

    def _merge_error(
        self,
        state: WorkflowState,
        logs: list[str],
        errors: list[dict[str, Any]],
        approvals: dict[str, Any],
    ) -> WorkflowState:
        next_state: WorkflowState = dict(state)
        next_state.update({"logs": logs, "errors": errors, "approvals": approvals})
        return next_state
