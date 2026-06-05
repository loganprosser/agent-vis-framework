"""Unified CLI runner for the agent-vis demos.

Usage:

    python -m examples.run <demo> [--provider <id>] [--inputs '<json>']
                                    [--preset <name>] [--format json|pretty]
                                    [--config-dir <path>]

Demos:

    research_assistant     — M4 ReAct orchestrator
    burr_code_review       — M2 burr_kit + M3 Mermaid runtime viz
    combinatorial_calc     — M2 testforge + SubprocessRunner (no LLM)
    hybrid_pipeline        — M4 → M2 composition

The runner loads the workflow YAML directly through ``GraphBuilder`` so
it doesn't require the FastAPI server to be running. Use ``--provider``
to override which model provider drives any LLM-backed nodes; the
provider id must exist in ``configs/models.yaml`` (register one with
``./configure-model.sh``). Use ``--preset`` to override the active preset
on burr_subsystem nodes that support it (currently
``demo_burr_code_review``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state

DEMOS: dict[str, dict[str, Any]] = {
    "research_assistant": {
        "workflow": "demo_react_research_assistant",
        "default_inputs": {"objective": "Explain combinatorial testing in two sentences."},
        "llm_required": True,
    },
    "burr_code_review": {
        "workflow": "demo_burr_code_review",
        "default_inputs": {
            "target_path": "examples/burr_code_review/sample_calc.py",
            "file_content": Path(
                "examples/burr_code_review/sample_calc.py"
            ).read_text(encoding="utf-8")
            if Path("examples/burr_code_review/sample_calc.py").exists()
            else "",
        },
        "llm_required": True,
        "preset_field": "preset",
        "preset_node": "review_subsystem",
    },
    "combinatorial_calc": {
        "workflow": "demo_combinatorial_calc",
        "default_inputs": {},
        "llm_required": False,
    },
    "hybrid_pipeline": {
        "workflow": "demo_hybrid_pipeline",
        "default_inputs": {"topic": "Apache Burr"},
        "llm_required": True,
    },
}


def _override_provider(workflow: Any, provider_id: str) -> None:
    """Force every node in the workflow to use ``provider_id``."""
    for node in workflow.nodes:
        node.provider = provider_id


def _override_preset(workflow: Any, demo_meta: dict[str, Any], preset: str) -> None:
    node_id = demo_meta.get("preset_node")
    field = demo_meta.get("preset_field", "preset")
    if not node_id:
        return
    for node in workflow.nodes:
        if node.id == node_id:
            cfg = dict(node.config or {})
            cfg[field] = preset
            node.config = cfg
            return


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.demo not in DEMOS:
        raise SystemExit(f"Unknown demo: {args.demo}. Choose from {sorted(DEMOS)}.")
    meta = DEMOS[args.demo]
    config_dir = Path(args.config_dir or "configs")
    loader = ConfigLoader(config_dir=config_dir)
    workflow = loader.load_workflow(meta["workflow"])

    if args.provider:
        _override_provider(workflow, args.provider)
    if args.preset:
        _override_preset(workflow, meta, args.preset)

    registry = ModelRegistry()
    for cfg in loader.load_models().providers:
        registry.register_provider_config(cfg)

    mcps = {s.id: s for s in loader.load_mcps().servers}
    tools = ToolRegistry(mcps)
    for cfg in loader.load_tools().tools:
        tools.register_tool_config(cfg)

    graph = GraphBuilder(registry, tools, config_loader=loader).compile(workflow)

    inputs = dict(meta["default_inputs"])
    if args.inputs:
        inputs.update(json.loads(args.inputs))

    state = initial_state(
        run_id=f"local-{args.demo}",
        workflow_name=meta["workflow"],
        inputs=inputs,
    )
    return await graph.ainvoke(state)


def _print(final: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(final, indent=2, default=str))
        return
    outputs = final.get("node_outputs") or {}
    errors = final.get("errors") or []
    print("\n=== node_outputs ===")
    for node_id, value in outputs.items():
        print(f"\n[{node_id}]")
        if isinstance(value, dict):
            for k, v in value.items():
                snippet = str(v)
                if len(snippet) > 600:
                    snippet = snippet[:600] + " …"
                print(f"  {k}: {snippet}")
        else:
            print(f"  {value}")
    if errors:
        print("\n=== errors ===")
        for err in errors:
            print(f"  - {err}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("demo", choices=sorted(DEMOS), help="Demo to run.")
    parser.add_argument(
        "--provider",
        default=None,
        help="Provider id from configs/models.yaml to use for every LLM node "
        "in the workflow (overrides each node's provider: field).",
    )
    parser.add_argument(
        "--inputs",
        default=None,
        help="JSON object merged on top of the demo's default inputs.",
    )
    parser.add_argument(
        "--preset",
        default=None,
        help="Preset name to apply to demos that honour a preset (currently burr_code_review).",
    )
    parser.add_argument(
        "--format", choices=("json", "pretty"), default="pretty", help="Output format."
    )
    parser.add_argument(
        "--config-dir", default=None, help="Override the configs/ directory."
    )
    args = parser.parse_args(argv)

    try:
        final = asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 - surface clean error to the user.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print(final, args.format)
    return 0


if __name__ == "__main__":
    sys.exit(main())
