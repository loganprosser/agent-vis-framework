from __future__ import annotations

import asyncio
import json
from importlib import import_module
from typing import Any, Mapping

from app.nodes.base import BaseNode
from app.schemas.node_io import NodeContext, NodeResult


class BurrSubsystemNode(BaseNode):
    """Run a Burr application as one node inside a parent workflow."""

    async def execute(self, context: NodeContext) -> NodeResult:
        timeout_seconds = self._timeout_seconds()
        operation = asyncio.to_thread(self._execute_sync, context)
        if timeout_seconds is None:
            return await operation
        try:
            return await asyncio.wait_for(operation, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' timed out after {timeout_seconds}s."
            ) from exc

    def _execute_sync(self, context: NodeContext) -> NodeResult:
        factory = self._load_factory()
        input_map = self._mapping_config("input_map")
        output_map = self._mapping_config("output_map")
        factory_inputs = {
            child_key: self._resolve_path(context.state, parent_path, "parent workflow")
            for child_key, parent_path in input_map.items()
        }

        try:
            candidate = factory(**factory_inputs)
            application = candidate.build() if hasattr(candidate, "build") else candidate
        except Exception as exc:  # noqa: BLE001 - include configured factory details.
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' failed to build "
                f"{self._factory_label()}: {exc}"
            ) from exc

        if not hasattr(application, "run"):
            raise RuntimeError(
                f"burr_subsystem factory {self._factory_label()} must return "
                "a Burr ApplicationBuilder or application."
            )

        try:
            final_state = self._run_application(application)
        except Exception as exc:  # noqa: BLE001 - normalize Burr execution errors.
            raise RuntimeError(
                f"burr_subsystem node '{self.config.id}' failed while running "
                f"{self._factory_label()}: {exc}"
            ) from exc

        serialized_state = self._serialize_state(final_state)
        values = {
            parent_key: self._resolve_path(serialized_state, child_path, "Burr final state")
            for parent_key, child_path in output_map.items()
        }
        return NodeResult(
            values=values,
            logs=[f"{self.config.id}: Burr subsystem completed"],
            artifact={"burr_final_state": serialized_state},
        )

    def _load_factory(self):
        try:
            import_module("burr")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "burr_subsystem requires Apache Burr. Install it with: pip install apache-burr"
            ) from exc

        app_module = self._required_string_config("app_module")
        app_factory = self._required_string_config("app_factory")
        try:
            module = import_module(app_module)
        except Exception as exc:  # noqa: BLE001 - report import failures with module name.
            raise RuntimeError(
                f"burr_subsystem could not import app module '{app_module}': {exc}"
            ) from exc

        try:
            return getattr(module, app_factory)
        except AttributeError as exc:
            raise RuntimeError(
                f"burr_subsystem app module '{app_module}' has no factory '{app_factory}'."
            ) from exc

    def _run_application(self, application: Any) -> Any:
        halt_after = self._string_list_config("halt_after")
        terminal_states = self._string_list_config("terminal_states")
        if halt_after and terminal_states:
            raise RuntimeError("burr_subsystem config may set halt_after or terminal_states, not both.")
        if halt_after:
            _, _, final_state = application.run(halt_after=halt_after)
            return final_state
        if terminal_states:
            return self._run_until_terminal_state(application, set(terminal_states))
        _, _, final_state = application.run()
        return final_state

    def _run_until_terminal_state(self, application: Any, terminal_states: set[str]) -> Any:
        final_state = application.state
        while application.has_next_action():
            _, _, final_state = application.step()
            if final_state.get("status") in terminal_states:
                return final_state
        raise RuntimeError(
            f"Burr application completed without reaching a terminal status in {sorted(terminal_states)}."
        )

    def _mapping_config(self, key: str) -> dict[str, Any]:
        value = self.config.config.get(key, {})
        if not isinstance(value, dict):
            raise RuntimeError(f"burr_subsystem config.{key} must be a mapping.")
        return value

    def _string_list_config(self, key: str) -> list[str]:
        value = self.config.config.get(key)
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise RuntimeError(f"burr_subsystem config.{key} must be a string or list of strings.")
        return value

    def _timeout_seconds(self) -> float | None:
        value = self.config.config.get("timeout_seconds")
        if value is None:
            return None
        try:
            timeout_seconds = float(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("burr_subsystem config.timeout_seconds must be a positive number.") from exc
        if timeout_seconds <= 0:
            raise RuntimeError("burr_subsystem config.timeout_seconds must be a positive number.")
        return timeout_seconds

    def _required_string_config(self, key: str) -> str:
        value = self.config.config.get(key)
        if not isinstance(value, str) or not value:
            raise RuntimeError(f"burr_subsystem config.{key} is required.")
        return value

    def _factory_label(self) -> str:
        return f"{self.config.config.get('app_module')}.{self.config.config.get('app_factory')}"

    @staticmethod
    def _resolve_path(data: Mapping[str, Any], path: Any, source_name: str) -> Any:
        if not isinstance(path, str) or not path:
            raise RuntimeError(f"burr_subsystem paths must be non-empty strings, got {path!r}.")
        value: Any = data
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                raise RuntimeError(f"burr_subsystem could not resolve '{path}' from {source_name}.")
            value = value[part]
        return value

    @staticmethod
    def _serialize_state(state: Any) -> dict[str, Any]:
        if hasattr(state, "get_all"):
            state = state.get_all()
        if not isinstance(state, Mapping):
            raise RuntimeError("Burr application final state must be mapping-like.")
        snapshot = {key: value for key, value in state.items() if not key.startswith("__")}
        return json.loads(json.dumps(snapshot, default=str))
