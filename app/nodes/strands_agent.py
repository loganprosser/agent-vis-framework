"""Run an Amazon Strands ``Agent`` as one node inside a parent workflow.

Mirrors the shape of :class:`BurrSubsystemNode`: the workflow YAML points
at a user Python factory, the node imports it, calls it once to obtain an
agent, then invokes the agent with a prompt resolved from workflow state.

The factory contract is intentionally permissive — :func:`inspect.signature`
chooses which optional kwargs to forward, so the same factory works whether
it accepts a model provider, no kwargs at all, or arbitrary other inputs
from ``input_map``.

Strands' Agent is callable: ``agent(prompt) -> AgentResult``. We extract
``.message.content[0].text`` when available, otherwise fall back to
``str(result)``. Tool calls and assistant messages, when observable via
``result.message`` / ``result.metrics``, are captured into the run's
artifacts and emitted as ``strands_tool_call`` / ``strands_message`` events.
"""

from __future__ import annotations

import inspect
import json
from importlib import import_module
from typing import Any

from app.core.runtime_events import safe_append_event
from app.nodes.base import BaseNode, NodeExecutionError
from app.schemas.node_io import NodeResult


class StrandsAgentNode(BaseNode):
    """Wrap a Strands ``Agent`` factory as an agent-vis workflow node."""

    async def run(self, state: dict[str, Any]) -> NodeResult:
        cfg = dict(self.config.config or {})
        agent_module = cfg.get("agent_module")
        agent_factory = cfg.get("agent_factory")
        if not agent_module or not agent_factory:
            raise NodeExecutionError(
                f"strands_agent node '{self.config.id}' requires agent_module + agent_factory in config."
            )

        run_id = state.get("run_id", "")
        safe_append_event(
            self.event_store,
            run_id,
            "strands_agent_started",
            node_id=self.config.id,
            payload={"agent_module": agent_module, "agent_factory": agent_factory},
        )

        factory_inputs = self._map_inputs(state, cfg.get("input_map") or {})
        try:
            agent = self._build_agent(agent_module, agent_factory, factory_inputs)
        except Exception as exc:  # noqa: BLE001 - normalise factory failures.
            safe_append_event(
                self.event_store,
                run_id,
                "strands_agent_failed",
                node_id=self.config.id,
                payload={"error": str(exc), "stage": "build"},
            )
            raise NodeExecutionError(f"strands_agent '{self.config.id}' build failed: {exc}") from exc

        prompt_key = cfg.get("prompt_key", "prompt")
        prompt = self._resolve_prompt(state, prompt_key, factory_inputs)
        if not prompt:
            raise NodeExecutionError(
                f"strands_agent '{self.config.id}' could not find prompt at key '{prompt_key}'."
            )

        try:
            result = agent(prompt)
        except Exception as exc:  # noqa: BLE001 - normalise agent errors.
            safe_append_event(
                self.event_store,
                run_id,
                "strands_agent_failed",
                node_id=self.config.id,
                payload={"error": str(exc), "stage": "invoke"},
            )
            raise NodeExecutionError(f"strands_agent '{self.config.id}' invoke failed: {exc}") from exc

        artifact = self._extract_artifact(result, prompt)

        for call in artifact.get("tool_calls", []):
            safe_append_event(
                self.event_store,
                run_id,
                "strands_tool_call",
                node_id=self.config.id,
                payload=call,
            )
        for message in artifact.get("messages", []):
            safe_append_event(
                self.event_store,
                run_id,
                "strands_message",
                node_id=self.config.id,
                payload=message,
            )
        safe_append_event(
            self.event_store,
            run_id,
            "strands_agent_completed",
            node_id=self.config.id,
            payload={"answer": artifact.get("answer", "")[:200]},
        )

        values = self._project_outputs(artifact, cfg.get("output_map") or {})
        return NodeResult(
            values=values or {"answer": artifact.get("answer", "")},
            logs=[f"{self.config.id}: Strands agent completed"],
            artifact=artifact,
        )

    def _build_agent(self, module_name: str, factory_name: str, factory_inputs: dict[str, Any]) -> Any:
        try:
            module = import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - report module errors with name.
            raise RuntimeError(f"cannot import {module_name}: {exc}") from exc
        try:
            factory = getattr(module, factory_name)
        except AttributeError as exc:
            raise RuntimeError(f"{module_name} has no factory {factory_name}") from exc
        if not callable(factory):
            raise RuntimeError(f"{module_name}.{factory_name} is not callable.")

        try:
            sig = inspect.signature(factory)
            allowed = set(sig.parameters)
        except (TypeError, ValueError):
            allowed = set()

        kwargs = {k: v for k, v in factory_inputs.items() if k in allowed}
        if "model_provider" in allowed:
            kwargs.setdefault("model_provider", self.model_provider)
        if "tools" in allowed:
            kwargs.setdefault("tools", self.tools)
        return factory(**kwargs)

    def _map_inputs(self, state: dict[str, Any], input_map: dict[str, str]) -> dict[str, Any]:
        inputs = state.get("inputs", {}) or {}
        outputs = state.get("node_outputs", {}) or {}
        resolved: dict[str, Any] = {}
        for dest, path in input_map.items():
            head, _, tail = path.partition(".")
            if head == "inputs":
                resolved[dest] = inputs.get(tail) if tail else inputs
            elif head == "node_outputs" and tail:
                resolved[dest] = outputs.get(tail)
            elif path in inputs:
                resolved[dest] = inputs[path]
            elif path in outputs:
                resolved[dest] = outputs[path]
            else:
                resolved[dest] = None
        return resolved

    def _resolve_prompt(self, state: dict[str, Any], key: str, factory_inputs: dict[str, Any]) -> str:
        if key in factory_inputs and factory_inputs[key]:
            return str(factory_inputs[key])
        inputs = state.get("inputs", {}) or {}
        if key in inputs:
            return str(inputs[key])
        return ""

    def _extract_artifact(self, result: Any, prompt: str) -> dict[str, Any]:
        answer = ""
        tool_calls: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        message = getattr(result, "message", None) or getattr(result, "final_message", None)
        if isinstance(message, dict):
            for block in message.get("content", []) or []:
                if isinstance(block, dict) and "text" in block:
                    answer += block["text"]
            messages.append({"role": message.get("role", "assistant"), "content": answer})
        elif isinstance(result, str):
            answer = result
        else:
            answer = str(result)

        for attr in ("tool_uses", "tool_calls", "calls"):
            calls = getattr(result, attr, None)
            if calls:
                for call in calls:
                    if isinstance(call, dict):
                        tool_calls.append(
                            {
                                "name": call.get("name") or call.get("toolUseId"),
                                "input": call.get("input"),
                                "output": call.get("output"),
                            }
                        )
                break

        return {
            "prompt": prompt,
            "answer": answer.strip(),
            "tool_calls": tool_calls,
            "messages": messages,
            "raw_type": type(result).__name__,
        }

    def _project_outputs(self, artifact: dict[str, Any], output_map: dict[str, str]) -> dict[str, Any]:
        if not output_map:
            return {}
        out: dict[str, Any] = {}
        for dest, path in output_map.items():
            head, _, tail = path.partition(".")
            value: Any
            if head == "artifact":
                value = artifact.get(tail) if tail else artifact
            elif path in artifact:
                value = artifact[path]
            else:
                value = None
            out[dest] = value if not isinstance(value, (dict, list)) else json.loads(json.dumps(value, default=str))
        return out
