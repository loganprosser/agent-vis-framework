"""ReAct loop orchestrator — a "pi-coding" node that picks among declared
tools, declared subagents, and MCP-discovered tools dynamically until it
emits a final answer.

Loop format (strict):

    Thought: <reasoning>
    Action: <name>
    Action Input: <json-or-empty>
    Observation: <appended by the framework>
    ... repeated until ...
    Thought: <reasoning>
    Action: final_answer
    Action Input: {"answer": "<text>"}

Each iteration emits ``react_thought``, ``react_action``, and
``react_observation`` events. The closing turn emits ``react_final``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.runtime_events import safe_append_event
from app.models.base import ModelRequest
from app.nodes.base import BaseNode, NodeExecutionError
from app.schemas.node_io import NodeResult
from app.tools.base import Tool

FINAL_ACTION = "final_answer"


@dataclass
class _ToolEntry:
    name: str
    description: str
    kind: str  # "tool" | "subagent" | "mcp"
    callable_: Any = None  # tool / subagent dispatcher
    source: str = ""


@dataclass
class _LoopRecord:
    thought: str
    action: str
    action_input: Any
    observation: str = ""


@dataclass
class _LoopResult:
    final_answer: str = ""
    iterations: list[_LoopRecord] = field(default_factory=list)
    stop_reason: str = "final_answer"


REACT_PROMPT = (
    "You are a tool-using agent that must reason in the ReAct format. "
    "On each turn, output exactly three lines:\n"
    "Thought: <one short sentence>\n"
    "Action: <one of the listed actions>\n"
    "Action Input: <single-line JSON, or {} if no input>\n\n"
    "After the framework appends an Observation, continue with another turn. "
    f"To finish, use Action: {FINAL_ACTION} and put your answer in "
    '"answer". Do not output anything outside the Thought/Action/Action Input format.'
)


_ACTION_LINE = re.compile(r"^Action:\s*(.+?)\s*$", re.MULTILINE)
_THOUGHT_LINE = re.compile(r"^Thought:\s*(.+?)\s*$", re.MULTILINE)
_INPUT_LINE = re.compile(r"^Action Input:\s*(.+?)\s*$", re.MULTILINE | re.DOTALL)


def _parse_turn(text: str) -> tuple[str, str, Any]:
    """Return (thought, action, action_input_obj) from one ReAct turn."""
    thought_match = _THOUGHT_LINE.search(text)
    action_match = _ACTION_LINE.search(text)
    input_match = _INPUT_LINE.search(text)

    thought = thought_match.group(1).strip() if thought_match else ""
    action = action_match.group(1).strip() if action_match else ""
    raw_input = input_match.group(1).strip() if input_match else "{}"

    # Action Input may span until the next ``Thought:`` / ``Observation:`` line.
    cutoff = re.search(r"\n(Thought:|Observation:)", raw_input)
    if cutoff:
        raw_input = raw_input[: cutoff.start()].strip()

    try:
        parsed_input = json.loads(raw_input) if raw_input else {}
    except json.JSONDecodeError:
        parsed_input = {"_raw": raw_input}
    return thought, action, parsed_input


class ReactOrchestratorNode(BaseNode):
    """Run a ReAct-style loop dispatching to declared tools / subagents / MCP-discovered tools."""

    async def run(self, state: dict[str, Any]) -> NodeResult:
        cfg = dict(self.config.config or {})
        objective_key = cfg.get("objective_key", "objective")
        max_iterations = int(cfg.get("max_iterations", 8))
        subagent_configs = cfg.get("subagents") or []
        mcp_discovery = cfg.get("mcp_discovery") or []

        objective = self._resolve_objective(state, objective_key)
        if not objective:
            raise NodeExecutionError(
                f"react_orchestrator '{self.config.id}' could not find objective at key '{objective_key}'."
            )

        catalog = await self._build_catalog(subagent_configs, mcp_discovery)
        if not catalog:
            raise NodeExecutionError(
                f"react_orchestrator '{self.config.id}' has an empty tool catalog."
            )

        loop = await self._run_loop(state, objective, catalog, max_iterations)

        artifact = {
            "objective": objective,
            "catalog": [
                {"name": e.name, "kind": e.kind, "source": e.source, "description": e.description}
                for e in catalog.values()
            ],
            "iterations": [
                {
                    "thought": rec.thought,
                    "action": rec.action,
                    "action_input": rec.action_input,
                    "observation": rec.observation,
                }
                for rec in loop.iterations
            ],
            "final_answer": loop.final_answer,
            "stop_reason": loop.stop_reason,
        }
        return NodeResult(
            values={"answer": loop.final_answer, "iterations": len(loop.iterations)},
            logs=[
                f"{self.config.id}: ReAct loop {loop.stop_reason} after {len(loop.iterations)} iterations"
            ],
            artifact=artifact,
        )

    def _resolve_objective(self, state: dict[str, Any], key: str) -> str:
        inputs = state.get("inputs", {}) or {}
        outputs = state.get("node_outputs", {}) or {}
        if key in inputs:
            return str(inputs[key])
        if key in outputs:
            value = outputs[key]
            return str(value) if not isinstance(value, dict) else json.dumps(value)
        return ""

    async def _build_catalog(
        self, subagents: list[dict[str, Any]], mcp_discovery: list[str]
    ) -> dict[str, _ToolEntry]:
        catalog: dict[str, _ToolEntry] = {}

        for tool_id, tool in (self.tools or {}).items():
            catalog[tool_id] = _ToolEntry(
                name=tool_id,
                description=getattr(tool, "description", "") or f"Declared tool {tool_id}",
                kind="tool",
                callable_=tool,
                source="declared",
            )

        for sub in subagents:
            name = sub.get("id") or sub.get("name")
            if not name:
                continue
            catalog[name] = _ToolEntry(
                name=name,
                description=sub.get("description") or f"Subagent {name}",
                kind="subagent",
                callable_=sub,
                source="declared",
            )

        for server_tool_id in mcp_discovery:
            mcp_tool = (self.tools or {}).get(server_tool_id)
            if mcp_tool is None:
                continue
            try:
                listing = await mcp_tool.run(action="list_tools")
            except Exception as exc:  # noqa: BLE001 - discovery is best-effort.
                catalog[f"{server_tool_id}__error"] = _ToolEntry(
                    name=f"{server_tool_id}__error",
                    description=f"MCP discovery failed: {exc}",
                    kind="mcp",
                    source=server_tool_id,
                )
                continue
            tools_payload = (listing.data or {}).get("tools") or (listing.data or {}).get("result") or []
            if isinstance(tools_payload, dict):
                tools_payload = tools_payload.get("tools") or []
            for tool_meta in tools_payload:
                tool_name = tool_meta.get("name") if isinstance(tool_meta, dict) else None
                if not tool_name:
                    continue
                qualified = f"{server_tool_id}.{tool_name}"
                catalog[qualified] = _ToolEntry(
                    name=qualified,
                    description=(tool_meta.get("description") or "")[:240],
                    kind="mcp",
                    callable_={"mcp_tool": mcp_tool, "remote_name": tool_name},
                    source=server_tool_id,
                )

        return catalog

    async def _run_loop(
        self,
        state: dict[str, Any],
        objective: str,
        catalog: dict[str, _ToolEntry],
        max_iterations: int,
    ) -> _LoopResult:
        run_id = state.get("run_id", "")
        transcript: list[str] = []
        result = _LoopResult()

        for i in range(max_iterations):
            user_message = self._compose_user_message(objective, catalog, transcript)
            response = await self.model_provider.generate(
                ModelRequest(
                    model=self.config.model or self.model_provider.default_model,
                    system_prompt=self.config.system_prompt or REACT_PROMPT,
                    messages=[{"role": "user", "content": user_message}],
                )
            )
            thought, action, action_input = _parse_turn(response.text)
            record = _LoopRecord(thought=thought, action=action, action_input=action_input)
            safe_append_event(
                self.event_store,
                run_id,
                "react_thought",
                node_id=self.config.id,
                payload={"iteration": i, "thought": thought},
            )
            safe_append_event(
                self.event_store,
                run_id,
                "react_action",
                node_id=self.config.id,
                payload={"iteration": i, "action": action, "input": action_input},
            )

            if action == FINAL_ACTION:
                result.final_answer = str(
                    action_input.get("answer") if isinstance(action_input, dict) else action_input
                )
                safe_append_event(
                    self.event_store,
                    run_id,
                    "react_final",
                    node_id=self.config.id,
                    payload={"iteration": i, "answer": result.final_answer},
                )
                result.iterations.append(record)
                return result

            entry = catalog.get(action)
            if entry is None:
                record.observation = f"unknown action '{action}'; pick one of: {sorted(catalog)}"
            else:
                record.observation = await self._dispatch(entry, action_input)
            safe_append_event(
                self.event_store,
                run_id,
                "react_observation",
                node_id=self.config.id,
                payload={"iteration": i, "observation": record.observation},
            )

            transcript.append(
                f"Thought: {thought}\nAction: {action}\nAction Input: {json.dumps(action_input)}\n"
                f"Observation: {record.observation}"
            )
            result.iterations.append(record)

        result.stop_reason = "max_iterations"
        return result

    def _compose_user_message(
        self, objective: str, catalog: dict[str, _ToolEntry], transcript: list[str]
    ) -> str:
        catalog_lines = ["Available actions:"] + [
            f"- {entry.name} ({entry.kind}): {entry.description}" for entry in catalog.values()
        ] + [f"- {FINAL_ACTION} (control): emit the final answer and stop."]
        history = "\n\n".join(transcript) if transcript else "(no prior turns)"
        return (
            f"Objective: {objective}\n\n"
            + "\n".join(catalog_lines)
            + f"\n\nPrior turns:\n{history}\n\nProduce the next turn."
        )

    async def _dispatch(self, entry: _ToolEntry, action_input: Any) -> str:
        try:
            if entry.kind == "tool":
                tool: Tool = entry.callable_
                kwargs = action_input if isinstance(action_input, dict) else {"input": action_input}
                result = await tool.run(**kwargs)
                return self._summarize_tool_result(result)
            if entry.kind == "subagent":
                sub = entry.callable_
                provider = self.model_provider
                user = (
                    action_input.get("message")
                    if isinstance(action_input, dict)
                    else str(action_input)
                ) or ""
                response = await provider.generate(
                    ModelRequest(
                        model=sub.get("model") or self.config.model or provider.default_model,
                        system_prompt=sub.get("system_prompt", ""),
                        messages=[{"role": "user", "content": user}],
                    )
                )
                return response.text.strip() or "(empty subagent response)"
            if entry.kind == "mcp":
                payload = entry.callable_
                mcp_tool = payload["mcp_tool"]
                remote_name = payload["remote_name"]
                arguments = action_input if isinstance(action_input, dict) else {"input": action_input}
                result = await mcp_tool.run(
                    action="call_tool", name=remote_name, arguments=arguments
                )
                return self._summarize_tool_result(result)
        except Exception as exc:  # noqa: BLE001 - report dispatch failures to the LLM.
            return f"dispatch error: {exc}"
        return f"unsupported entry kind: {entry.kind}"

    def _summarize_tool_result(self, result: Any) -> str:
        if result is None:
            return "(no result)"
        data = getattr(result, "data", None)
        error = getattr(result, "error", None)
        ok = getattr(result, "ok", True)
        if not ok and error:
            return f"error: {error}"
        if data is None:
            return "(no data)"
        try:
            return json.dumps(data, default=str)[:2000]
        except Exception:  # noqa: BLE001
            return str(data)[:2000]
