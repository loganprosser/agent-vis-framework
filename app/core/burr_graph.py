"""Render a Burr ``ApplicationGraph`` as Mermaid ``graph TD`` text.

Ported from ``burr-combinatorial-testing/src/atf/viz.py``. Used by the
``GET /workflows/{name}/subsystems/{node_id}/graph`` endpoint to feed the
React inspector's live runtime visualizer.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from importlib import import_module
from typing import Any

_MERMAID_SAFE = str.maketrans({'"': "'", "`": "'", "\n": " "})


@dataclass
class SubsystemGraph:
    mermaid: str
    actions: list[str]
    entrypoint: str
    transitions: list[dict[str, str]]


def _safe_label(text: str) -> str:
    return text.translate(_MERMAID_SAFE).strip()


def _node_id(name: str) -> str:
    return "n_" + "".join(c if c.isalnum() else "_" for c in name)


def graph_to_mermaid(app_graph: Any, *, include_conditions: bool = True) -> str:
    """Convert a Burr ``ApplicationGraph`` to a Mermaid ``graph TD`` string."""
    lines: list[str] = ["graph TD"]
    entrypoint_name = getattr(getattr(app_graph, "entrypoint", None), "name", None)
    action_names = [a.name for a in app_graph.actions]

    for name in action_names:
        label = _safe_label(name)
        node_id = _node_id(name)
        if name == entrypoint_name:
            lines.append(f'    {node_id}(["▶ {label}"]):::entry')
        elif name == "error_out":
            lines.append(f'    {node_id}["{label}"]:::error')
        elif name.startswith("write_") or "report" in name:
            lines.append(f'    {node_id}["{label}"]:::report')
        else:
            lines.append(f'    {node_id}["{label}"]')

    for transition in app_graph.transitions:
        from_id = _node_id(transition.from_.name)
        to_id = _node_id(transition.to.name)
        cond_name = getattr(transition.condition, "name", None) or "default"
        is_default = cond_name == "default"
        if include_conditions and not is_default:
            label = _safe_label(cond_name)
            lines.append(f'    {from_id} -- "{label}" --> {to_id}')
        elif is_default:
            lines.append(f"    {from_id} -. default .-> {to_id}")
        else:
            lines.append(f"    {from_id} --> {to_id}")

    lines.extend(
        [
            "    classDef entry fill:#10b981,stroke:#34d399,color:#0b1220,font-weight:bold;",
            "    classDef error fill:#7f1d1d,stroke:#f87171,color:#fee2e2;",
            "    classDef report fill:#1e3a8a,stroke:#60a5fa,color:#dbeafe;",
            "    classDef current fill:#fbbf24,stroke:#fde047,color:#0b1220,font-weight:bold;",
        ]
    )
    return "\n".join(lines)


def render_subsystem_graph(app_module: str, app_factory: str) -> SubsystemGraph:
    """Import a Burr factory, build it with no inputs, and return its graph.

    Factories that require inputs to build are called with a single
    ``__inspect=True`` flag they can ignore — if that fails, we raise so the
    caller can return a structured 500. The application is never *run*.
    """
    module = import_module(app_module)
    factory = getattr(module, app_factory)
    # Build placeholder kwargs for any required positional parameters so the
    # graph can be inspected without running the workflow.
    try:
        sig = inspect.signature(factory)
        placeholders = {
            name: f"<inspect:{name}>"
            for name, param in sig.parameters.items()
            if param.default is inspect.Parameter.empty
            and param.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
    except (TypeError, ValueError):
        placeholders = {}
    candidate = factory(**placeholders)
    application = candidate.build() if hasattr(candidate, "build") else candidate

    app_graph = application.graph
    return SubsystemGraph(
        mermaid=graph_to_mermaid(app_graph),
        actions=[a.name for a in app_graph.actions],
        entrypoint=getattr(getattr(app_graph, "entrypoint", None), "name", "") or "",
        transitions=[
            {
                "from": t.from_.name,
                "to": t.to.name,
                "condition": getattr(t.condition, "name", None) or "default",
            }
            for t in app_graph.transitions
        ],
    )


def node_id_for(name: str) -> str:
    """Public mapping used by the frontend to highlight the current action."""
    return _node_id(name)
