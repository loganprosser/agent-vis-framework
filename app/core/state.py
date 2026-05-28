from __future__ import annotations

from typing import Any

from typing_extensions import TypedDict


class WorkflowState(TypedDict, total=False):
    """Shared state passed through LangGraph nodes.

    LangGraph merges dictionaries returned by each node. Keeping this state
    generic makes it usable for document, code, test, research, or ops workflows.
    """

    run_id: str
    workflow_name: str
    inputs: dict[str, Any]
    artifacts: dict[str, Any]
    node_outputs: dict[str, Any]
    errors: list[dict[str, Any]]
    logs: list[str]
    approvals: dict[str, Any]
    final_report: str | None


def initial_state(
    *,
    run_id: str,
    workflow_name: str,
    inputs: dict[str, Any],
) -> WorkflowState:
    return {
        "run_id": run_id,
        "workflow_name": workflow_name,
        "inputs": inputs,
        "artifacts": {},
        "node_outputs": {},
        "errors": [],
        "logs": [],
        "approvals": {},
        "final_report": None,
    }
