from __future__ import annotations

import asyncio
from abc import ABC
from collections.abc import Mapping
from typing import Any

from app.core.runtime_events import RuntimeEventStore, bind_runtime_event_context, safe_append_event
from app.core.state import WorkflowState
from app.models.base import ModelProvider, ModelRequest
from app.schemas.node_io import NodeContext, NodeResult
from app.schemas.workflow import NodeConfig
from app.tools.base import Tool


class NodeExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        artifact: Any | None = None,
        subsystem_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.artifact = artifact
        self.subsystem_metadata = subsystem_metadata


class BaseNode(ABC):
    def __init__(
        self,
        config: NodeConfig,
        model_provider: ModelProvider,
        tools: dict[str, Tool] | None = None,
        event_store: RuntimeEventStore | None = None,
    ) -> None:
        self.config = config
        self.model_provider = model_provider
        self.tools = tools or {}
        self.event_store = event_store

    async def __call__(self, state: WorkflowState) -> WorkflowState:
        run_id = state.get("run_id", "")
        self._append_event(run_id, "node_started", status="running")
        with bind_runtime_event_context(run_id, self.config.id):
            return await self._execute_with_retries(state, run_id)

    async def _execute_with_retries(self, state: WorkflowState, run_id: str) -> WorkflowState:
        logs = list(state.get("logs", []))
        errors = list(state.get("errors", []))
        approvals = dict(state.get("approvals", {}))
        error_artifact: Any | None = None
        error_subsystem_metadata: dict[str, Any] | None = None

        if self.config.human_approval:
            approvals[self.config.id] = {
                "required": True,
                "status": "auto_approved_for_mock_run",
            }

        for attempt in range(1, self.config.retry_policy.max_attempts + 1):
            try:
                result = await self.execute(self.create_context(state))
                next_state = self._merge_success(state, result, logs, approvals)
                self._append_event(
                    run_id,
                    "node_completed",
                    status="completed",
                    artifact_names=self._artifact_names(
                        result.values if result.artifact is None else result.artifact
                    ),
                )
                return next_state
            except Exception as exc:  # noqa: BLE001 - capture node errors into workflow state.
                if getattr(exc, "artifact", None) is not None:
                    error_artifact = exc.artifact
                if getattr(exc, "subsystem_metadata", None) is not None:
                    error_subsystem_metadata = exc.subsystem_metadata
                logs.append(f"{self.config.id}: attempt {attempt} failed: {exc}")
                if attempt >= self.config.retry_policy.max_attempts:
                    errors.append({"node_id": self.config.id, "message": str(exc)})
                    self._append_event(
                        run_id,
                        "node_failed",
                        status="failed",
                        artifact_names=self._artifact_names(error_artifact),
                        error=str(exc),
                    )
                    return self._merge_error(
                        state,
                        logs,
                        errors,
                        approvals,
                        error_artifact,
                        error_subsystem_metadata,
                    )
                if self.config.retry_policy.backoff_seconds:
                    await asyncio.sleep(self.config.retry_policy.backoff_seconds)

        self._append_event(run_id, "node_failed", status="failed")
        return self._merge_error(
            state,
            logs,
            errors,
            approvals,
            error_artifact,
            error_subsystem_metadata,
        )

    async def execute(self, context: NodeContext) -> NodeResult:
        """Execute a node and normalize legacy dictionary outputs."""

        output = await self.run(context.state)
        if isinstance(output, NodeResult):
            return output
        return NodeResult(values=output)

    async def run(self, state: WorkflowState) -> dict[str, Any] | NodeResult:
        """Return this node's output payload.

        Existing nodes implement this state-based hook. New execution layers can
        override execute() when they need the typed NodeContext boundary.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement execute() or run().")

    def create_context(self, state: WorkflowState) -> NodeContext:
        return NodeContext(node_id=self.config.id, state=state, values=self.context(state))

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
        result: NodeResult,
        logs: list[str],
        approvals: dict[str, Any],
    ) -> WorkflowState:
        output = result.values
        node_outputs = dict(state.get("node_outputs", {}))
        artifacts = dict(state.get("artifacts", {}))
        subsystems = dict(state.get("_subsystems", {}))
        node_outputs[self.config.id] = output
        artifacts[self.config.id] = output if result.artifact is None else result.artifact
        if result.subsystem_metadata is not None:
            subsystems[self.config.id] = result.subsystem_metadata
        logs.extend(result.logs)
        logs.append(f"{self.config.id}: completed")

        next_state: WorkflowState = dict(state)
        next_state.update(
            {
                "node_outputs": node_outputs,
                "artifacts": artifacts,
                "_subsystems": subsystems,
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
        artifact: Any | None = None,
        subsystem_metadata: dict[str, Any] | None = None,
    ) -> WorkflowState:
        next_state: WorkflowState = dict(state)
        artifacts = dict(state.get("artifacts", {}))
        subsystems = dict(state.get("_subsystems", {}))
        if artifact is not None:
            artifacts[self.config.id] = artifact
        if subsystem_metadata is not None:
            subsystems[self.config.id] = subsystem_metadata
        next_state.update(
            {
                "logs": logs,
                "errors": errors,
                "approvals": approvals,
                "artifacts": artifacts,
                "_subsystems": subsystems,
            }
        )
        return next_state

    def _append_event(
        self,
        run_id: str,
        event_type: str,
        *,
        status: str,
        artifact_names: list[str] | None = None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "node_id": self.config.id,
            "node_type": self.config.type,
            "status": status,
        }
        if artifact_names:
            payload["artifact_names"] = artifact_names
        if error:
            payload["error"] = error
        safe_append_event(
            self.event_store,
            run_id,
            event_type,
            node_id=self.config.id,
            payload=payload,
        )

    @staticmethod
    def _artifact_names(artifact: Any) -> list[str]:
        if not isinstance(artifact, Mapping):
            return []
        return sorted(str(name) for name in artifact)
