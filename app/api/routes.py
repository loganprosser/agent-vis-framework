from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.run_store import RunRecord, create_run_store
from app.core.state import initial_state
from app.schemas.workflow import WorkflowConfig

router = APIRouter()
config_loader = ConfigLoader()
run_store = create_run_store()


class RunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


def build_registries() -> tuple[ModelRegistry, ToolRegistry]:
    model_registry = ModelRegistry()
    for provider_config in config_loader.load_models().providers:
        model_registry.register_provider_config(provider_config)

    mcp_servers = {server.id: server for server in config_loader.load_mcps().servers}
    tool_registry = ToolRegistry(mcp_servers)
    for tool_config in config_loader.load_tools().tools:
        tool_registry.register_tool_config(tool_config)

    return model_registry, tool_registry


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/workflows")
async def list_workflows() -> dict[str, list[str]]:
    return {"workflows": config_loader.list_workflows()}


@router.get("/workflows/{workflow_name}")
async def get_workflow(workflow_name: str) -> dict[str, Any]:
    if workflow_name not in config_loader.list_workflows():
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_name}")
    return config_loader.load_workflow(workflow_name).model_dump()


@router.put("/workflows/{workflow_name}")
async def save_workflow(workflow_name: str, workflow: WorkflowConfig) -> dict[str, Any]:
    try:
        saved = config_loader.save_workflow(workflow_name, workflow)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"workflow": saved.model_dump(), "saved": True}


@router.post("/workflows/validate")
async def validate_workflow(workflow: WorkflowConfig) -> dict[str, Any]:
    return {"valid": True, "workflow": workflow.model_dump()}


@router.post("/workflows/{workflow_name}/run", response_model=RunRecord)
async def run_workflow(workflow_name: str, request: RunRequest) -> RunRecord:
    if workflow_name not in config_loader.list_workflows():
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_name}")

    run = run_store.create(workflow_name, request.inputs)
    run_store.mark_running(run.run_id)
    state = initial_state(run_id=run.run_id, workflow_name=workflow_name, inputs=request.inputs)

    try:
        workflow = config_loader.load_workflow(workflow_name)
        model_registry, tool_registry = build_registries()
        graph = GraphBuilder(model_registry, tool_registry).compile(workflow)
        final_state = await graph.ainvoke(state)
    except Exception as exc:  # noqa: BLE001 - convert framework errors into run records.
        return run_store.mark_failed(run.run_id, str(exc), state)

    return run_store.mark_completed(run.run_id, final_state)


@router.get("/runs/{run_id}", response_model=RunRecord)
async def get_run(run_id: str) -> RunRecord:
    run = run_store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run
