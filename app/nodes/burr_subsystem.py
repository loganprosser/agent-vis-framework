from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Mapping

from app.core.runtime_events import safe_append_event
from app.nodes.base import NodeExecutionError
from app.nodes.subsystem import BaseSubsystemNode
from app.schemas.node_io import NodeContext, NodeResult
from app.schemas.workflow import BurrSubsystemConfig

BURR_JSON_ARTIFACT_NAMES = (
    "burr_final_state.json",
    "burr_node_metadata.json",
    "burr_trace.json",
)


@dataclass
class _ExecutionTracker:
    artifact: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latest_state: dict[str, Any] | None = None
    trace: list[dict[str, Any]] | None = None
    action_started_at: dict[int, datetime] = field(default_factory=dict)
    has_internal_trace: bool = False


class BurrSubsystemNode(BaseSubsystemNode):
    """Run a Burr application as one node inside a parent workflow."""

    subsystem_type = "burr_subsystem"

    async def execute(self, context: NodeContext) -> NodeResult:
        tracker = _ExecutionTracker()
        self._append_burr_event(context.state, "burr_subsystem_started", status="running")
        operation = asyncio.to_thread(self._execute_sync, context, tracker)
        timeout_seconds = self.burr_config.timeout_seconds
        if timeout_seconds is None:
            try:
                result = await operation
            except Exception as exc:  # noqa: BLE001 - normalize subsystem failures.
                return self._handle_failure(exc, tracker, context.state)
            self._append_burr_event(
                context.state,
                "burr_subsystem_completed",
                status="completed",
                tracker=tracker,
            )
            return result
        try:
            result = await asyncio.wait_for(operation, timeout=timeout_seconds)
        except TimeoutError as exc:
            return self._handle_failure(
                NodeExecutionError(
                    f"burr_subsystem node '{self.config.id}' timed out after {timeout_seconds}s.",
                ),
                tracker,
                context.state,
                status="timed_out",
            )
        except Exception as exc:  # noqa: BLE001 - normalize subsystem failures.
            return self._handle_failure(exc, tracker, context.state)
        self._append_burr_event(
            context.state,
            "burr_subsystem_completed",
            status="completed",
            tracker=tracker,
        )
        return result

    @property
    def burr_config(self) -> BurrSubsystemConfig:
        return BurrSubsystemConfig.model_validate(self.config.config)

    def _execute_sync(self, context: NodeContext, tracker: _ExecutionTracker) -> NodeResult:
        factory = self._load_factory()
        factory_inputs = self.map_inputs(context.state, self.burr_config.input_map)
        self._inject_provider_kwargs(factory_inputs)

        try:
            candidate = factory(**factory_inputs)
            if callable(getattr(candidate, "with_hooks", None)):
                # Burr lifecycle hooks must be attached to the builder before build().
                # Factories returning an already-built app retain the minimal trace fallback.
                candidate = candidate.with_hooks(self._create_trace_hook(tracker, context.state))
                tracker.has_internal_trace = True
            application = candidate.build() if hasattr(candidate, "build") else candidate
        except Exception as exc:  # noqa: BLE001 - include configured factory details.
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' failed to build "
                f"{self._factory_label()}: {exc}"
            ) from exc

        if not callable(getattr(application, "run", None)):
            raise RuntimeError(
                f"burr_subsystem factory {self._factory_label()} did not return a runnable "
                "Burr ApplicationBuilder or application."
            )

        self._start_tracking(tracker, application.state)
        try:
            final_state = self._run_application(application)
        except Exception as exc:  # noqa: BLE001 - normalize Burr execution errors.
            self._finish_tracking(tracker, application.state, status="failed")
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' failed while running "
                f"{self._factory_label()}: {exc}"
            ) from exc

        serialized_state = self._serialize_state(final_state)
        tracker.latest_state = serialized_state
        values = self.map_outputs(
            serialized_state,
            self.burr_config.output_map,
            source_name="Burr final state",
        )
        self._finish_tracking(tracker, serialized_state, status="completed")
        return NodeResult(
            values=values,
            logs=[f"{self.config.id}: Burr subsystem completed"],
            artifact=tracker.artifact,
            subsystem_metadata=self._subsystem_metadata(tracker),
        )

    def _load_factory(self):
        try:
            import_module("burr")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' requires Apache Burr. "
                "Install it with: pip install apache-burr"
            ) from exc

        app_module = self.burr_config.app_module
        app_factory = self.burr_config.app_factory
        try:
            module = import_module(app_module)
        except Exception as exc:  # noqa: BLE001 - report import failures with module name.
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' could not import "
                f"app module '{app_module}': {exc}"
            ) from exc

        try:
            factory = getattr(module, app_factory)
        except AttributeError as exc:
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' app module '{app_module}' "
                f"has no factory '{app_factory}'."
            ) from exc
        if not callable(factory):
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' factory "
                f"'{app_module}.{app_factory}' is not callable."
            )
        return factory

    def _inject_provider_kwargs(self, factory_inputs: dict[str, Any]) -> None:
        """Forward resolved model provider details to the Burr factory so it
        uses the same model configured in the workflow YAML instead of env vars.

        Only injects kwargs that the factory actually accepts (inspected via
        signature). This is provider-agnostic — any factory can opt into
        receiving model/provider info by declaring the matching parameters.
        """
        import inspect

        provider = self.model_provider
        model = self.config.model or provider.default_model

        available: dict[str, Any] = {
            "provider_id": provider.provider_id,
            "model": model,
        }
        if base_url := provider.config.get("base_url"):
            available["base_url"] = base_url

        # Legacy Ollama-specific kwargs — kept for backward compat with
        # existing factories that expect ollama_model / ollama_base_url
        from app.models.ollama_provider import OllamaModelProvider
        if isinstance(provider, OllamaModelProvider):
            available["ollama_model"] = model
            available["ollama_base_url"] = provider.config.get("base_url") or "http://127.0.0.1:11434"

        # Only inject kwargs the factory actually accepts
        factory = self._load_factory()
        sig = inspect.signature(factory)
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        for key, value in available.items():
            if key not in factory_inputs:
                if accepts_kwargs or key in sig.parameters:
                    factory_inputs[key] = value

    def _run_application(self, application: Any) -> Any:
        halt_after = self.burr_config.halt_after
        terminal_states = self.burr_config.terminal_states
        if halt_after:
            _, _, final_state = application.run(halt_after=halt_after)
            return final_state
        if terminal_states:
            return self._run_until_terminal_state(application, set(terminal_states))
        raise AssertionError("Burr subsystem config validation requires a halt condition.")

    def _run_until_terminal_state(self, application: Any, terminal_states: set[str]) -> Any:
        final_state = application.state
        while application.has_next_action():
            _, _, final_state = application.step()
            if final_state.get("status") in terminal_states:
                return final_state
        raise RuntimeError(
            f"Burr application completed without reaching a terminal status in {sorted(terminal_states)}."
        )

    def _factory_label(self) -> str:
        return f"{self.burr_config.app_module}.{self.burr_config.app_factory}"

    def _create_trace_hook(self, tracker: _ExecutionTracker, parent_state: Mapping[str, Any]) -> Any:
        lifecycle = import_module("burr.lifecycle")
        serialize_state = self._serialize_state
        serialize_value = self._serialize_value
        append_event = self._append_burr_event

        class BurrTraceHook(lifecycle.PreRunStepHook, lifecycle.PostRunStepHook):
            def pre_run_step(
                self,
                *,
                state: Any,
                action: Any,
                inputs: dict[str, Any],
                sequence_id: int,
                **future_kwargs: Any,
            ) -> None:
                started_at = datetime.now(UTC)
                tracker.action_started_at[sequence_id] = started_at
                tracker.trace = list(tracker.trace or [])
                tracker.trace.append(
                    {
                        "event": "action_start",
                        "timestamp": started_at.isoformat(),
                        "sequence_id": sequence_id,
                        "action": action.name,
                        "inputs": serialize_value(
                            {key: value for key, value in inputs.items() if not key.startswith("__")}
                        ),
                        "state": serialize_state(state),
                    }
                )
                append_event(
                    parent_state,
                    "burr_action_started",
                    status="running",
                    action=action.name,
                    sequence_id=sequence_id,
                )

            def post_run_step(
                self,
                *,
                state: Any,
                action: Any,
                result: dict[str, Any] | None,
                sequence_id: int,
                exception: Exception | None,
                **future_kwargs: Any,
            ) -> None:
                finished_at = datetime.now(UTC)
                started_at = tracker.action_started_at.pop(sequence_id, None)
                tracker.trace = list(tracker.trace or [])
                tracker.trace.append(
                    {
                        "event": "action_end",
                        "timestamp": finished_at.isoformat(),
                        "sequence_id": sequence_id,
                        "action": action.name,
                        "status": "failed" if exception else "completed",
                        "duration_ms": (
                            round((finished_at - started_at).total_seconds() * 1000, 3)
                            if started_at
                            else None
                        ),
                        "result": serialize_value(result),
                        "exception": str(exception) if exception else None,
                        "state": serialize_state(state),
                    }
                )
                append_event(
                    parent_state,
                    "burr_action_failed" if exception else "burr_action_completed",
                    status="failed" if exception else "completed",
                    action=action.name,
                    sequence_id=sequence_id,
                    duration_ms=(
                        round((finished_at - started_at).total_seconds() * 1000, 3)
                        if started_at
                        else None
                    ),
                    error=str(exception) if exception else None,
                )

        return BurrTraceHook()

    def _start_tracking(self, tracker: _ExecutionTracker, state: Any) -> None:
        tracker.started_at = datetime.now(UTC)
        tracker.latest_state = self._serialize_state(state)
        tracker.trace = [
            {
                "event": "start",
                "timestamp": tracker.started_at.isoformat(),
                "state": tracker.latest_state,
            }
        ]
        tracker.artifact = self._artifact_bundle(tracker, status="running")

    def _finish_tracking(self, tracker: _ExecutionTracker, state: Any, *, status: str) -> None:
        if tracker.finished_at is not None:
            return
        tracker.finished_at = datetime.now(UTC)
        tracker.latest_state = self._serialize_state(state)
        tracker.trace = list(tracker.trace or [])
        tracker.trace.append(
            {
                "event": "end",
                "timestamp": tracker.finished_at.isoformat(),
                "status": status,
                "state": tracker.latest_state,
            }
        )
        tracker.artifact = self._artifact_bundle(tracker, status=status)

    def _artifact_bundle(self, tracker: _ExecutionTracker, *, status: str) -> dict[str, Any]:
        final_state = tracker.latest_state or {}
        metadata = {
            "node_id": self.config.id,
            "runtime": "burr",
            "app_module": self.burr_config.app_module,
            "app_factory": self.burr_config.app_factory,
            "started_at": tracker.started_at.isoformat() if tracker.started_at else None,
            "finished_at": tracker.finished_at.isoformat() if tracker.finished_at else None,
            "status": status,
            "terminal_state": final_state.get("status"),
            "halt_reason": self._halt_reason(status, final_state),
            "duration_ms": self._duration_ms(tracker),
            "input_keys": list(self.burr_config.input_map),
            "output_keys": list(self.burr_config.output_map),
            "input_map": self.burr_config.input_map,
            "output_map": self.burr_config.output_map,
            "has_internal_trace": tracker.has_internal_trace,
            "artifact_names": self._json_artifact_names(),
        }
        return {
            self.burr_config.artifact_name: final_state,
            "burr_final_state.json": final_state,
            "burr_node_metadata.json": metadata,
            "burr_trace.json": {
                "source": "burr_lifecycle_hooks" if tracker.has_internal_trace else "minimal",
                "events": list(tracker.trace or []),
                "final_state": final_state,
            },
        }

    def _subsystem_metadata(self, tracker: _ExecutionTracker) -> dict[str, Any]:
        if tracker.artifact is None:
            return {}
        return tracker.artifact["burr_node_metadata.json"]

    def _halt_reason(self, status: str, final_state: Mapping[str, Any]) -> str:
        if status != "completed":
            return status
        if self.burr_config.halt_after:
            return f"halt_after: {', '.join(self.burr_config.halt_after)}"
        return f"terminal_state: {final_state.get('status')}"

    @staticmethod
    def _json_artifact_names() -> list[str]:
        return list(BURR_JSON_ARTIFACT_NAMES)

    @staticmethod
    def _duration_ms(tracker: _ExecutionTracker) -> float | None:
        if tracker.started_at is None or tracker.finished_at is None:
            return None
        return round((tracker.finished_at - tracker.started_at).total_seconds() * 1000, 3)

    def _handle_failure(
        self,
        exc: Exception,
        tracker: _ExecutionTracker,
        parent_state: Mapping[str, Any],
        *,
        status: str = "failed",
    ) -> NodeResult:
        if tracker.started_at is not None and tracker.finished_at is None:
            self._finish_tracking(tracker, tracker.latest_state or {}, status=status)
        error = (
            exc
            if isinstance(exc, NodeExecutionError)
            else NodeExecutionError(str(exc))
        )
        error.artifact = tracker.artifact
        error.subsystem_metadata = self._subsystem_metadata(tracker)
        self._append_burr_event(
            parent_state,
            "burr_subsystem_failed",
            status=status,
            tracker=tracker,
            error=str(error),
        )
        if self.burr_config.fail_on_error:
            raise error
        return NodeResult(
            logs=[f"{self.config.id}: Burr subsystem failed but fail_on_error is false: {error}"],
            artifact=error.artifact,
            subsystem_metadata=error.subsystem_metadata,
        )

    @staticmethod
    def _serialize_state(state: Any) -> dict[str, Any]:
        if hasattr(state, "get_all"):
            state = state.get_all()
        if not isinstance(state, Mapping):
            raise RuntimeError("Burr application final state must be mapping-like.")
        snapshot = {key: value for key, value in state.items() if not key.startswith("__")}
        return BurrSubsystemNode._serialize_value(snapshot)

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))

    def _append_burr_event(
        self,
        parent_state: Mapping[str, Any],
        event_type: str,
        *,
        status: str,
        tracker: _ExecutionTracker | None = None,
        action: str | None = None,
        sequence_id: int | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "node_id": self.config.id,
            "node_type": self.config.type,
            "runtime": "burr",
            "status": status,
            "app_module": self.config.config.get("app_module"),
            "app_factory": self.config.config.get("app_factory"),
        }
        if tracker is not None:
            payload["artifact_names"] = self._artifact_names(tracker.artifact)
            payload["duration_ms"] = self._duration_ms(tracker)
            payload["terminal_state"] = (tracker.latest_state or {}).get("status")
        if action is not None:
            payload["action"] = action
        if sequence_id is not None:
            payload["sequence_id"] = sequence_id
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if error:
            payload["error"] = error
        safe_append_event(
            self.event_store,
            parent_state.get("run_id"),
            event_type,
            node_id=self.config.id,
            payload=payload,
        )
