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


class RunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class PromptContent(BaseModel):
    content: str


def build_registries(config_loader: ConfigLoader | None = None) -> tuple[ModelRegistry, ToolRegistry]:
    config_loader = config_loader or ConfigLoader()
    model_registry = ModelRegistry()
    for provider_config in config_loader.load_models().providers:
        model_registry.register_provider_config(provider_config)

    mcp_servers = {server.id: server for server in config_loader.load_mcps().servers}
    tool_registry = ToolRegistry(mcp_servers)
    for tool_config in config_loader.load_tools().tools:
        tool_registry.register_tool_config(tool_config)

    return model_registry, tool_registry


def create_router(
    config_loader: ConfigLoader | None = None,
    run_store: Any | None = None,
) -> APIRouter:
    config_loader = config_loader or ConfigLoader()
    run_store = run_store or create_run_store()
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/catalog")
    async def catalog() -> dict[str, Any]:
        models = config_loader.load_models()
        tools = config_loader.load_tools()
        mcps = config_loader.load_mcps()
        providers = []
        for p in models.providers:
            providers.append({"id": p.id, "type": p.type, "default_model": p.default_model})
        tool_list = []
        for t in tools.tools:
            tool_list.append({"id": t.id, "type": t.type, "enabled": t.enabled})
        mcp_list = []
        for s in mcps.servers:
            mcp_list.append({"id": s.id, "name": s.name, "transport": s.transport, "enabled": s.enabled})
        return {"providers": providers, "tools": tool_list, "mcps": mcp_list}

    @router.get("/workflows")
    async def list_workflows() -> dict[str, list[str]]:
        return {"workflows": config_loader.list_workflows()}

    @router.get("/workflows/{workflow_name}")
    async def get_workflow(workflow_name: str) -> dict[str, Any]:
        if workflow_name not in config_loader.list_workflows():
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_name}")
        workflow = config_loader.load_workflow(workflow_name)
        data = workflow.model_dump(exclude_none=True)
        for node_data in data.get("nodes", []):
            if node_data.get("system_prompt_file"):
                node_config = next(n for n in workflow.nodes if n.id == node_data["id"])
                node_data["resolved_system_prompt"] = config_loader.resolve_system_prompt(node_config)
        return data

    @router.put("/workflows/{workflow_name}")
    async def save_workflow(workflow_name: str, workflow: WorkflowConfig) -> dict[str, Any]:
        try:
            for node in workflow.nodes:
                if node.system_prompt_file and node.system_prompt:
                    try:
                        config_loader.save_prompt(node.system_prompt_file, node.system_prompt)
                    except (ValueError, OSError) as exc:
                        raise HTTPException(status_code=400, detail=str(exc)) from exc
            saved = config_loader.save_workflow(workflow_name, workflow)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"workflow": saved.model_dump(exclude_none=True), "saved": True}

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
            model_registry, tool_registry = build_registries(config_loader)
            graph = GraphBuilder(model_registry, tool_registry, config_loader=config_loader).compile(workflow)
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

    # --- Prompt file endpoints ---

    @router.get("/prompts")
    async def list_prompts() -> dict[str, list[str]]:
        return {"prompts": config_loader.list_prompts()}

    @router.get("/prompts/{prompt_file:path}")
    async def get_prompt(prompt_file: str) -> dict[str, str]:
        try:
            content = config_loader.load_prompt(prompt_file)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"file": prompt_file, "content": content}

    @router.put("/prompts/{prompt_file:path}")
    async def save_prompt(prompt_file: str, body: PromptContent) -> dict[str, Any]:
        try:
            saved = config_loader.save_prompt(prompt_file, body.content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"file": saved, "saved": True}

    @router.delete("/prompts/{prompt_file:path}")
    async def delete_prompt(prompt_file: str) -> dict[str, Any]:
        try:
            config_loader.delete_prompt(prompt_file)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"deleted": True}

    return router


router = create_router()
