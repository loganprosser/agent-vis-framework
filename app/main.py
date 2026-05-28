from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router
from app.ui import workflow_editor

app = FastAPI(
    title="Agentic Workflow Framework",
    version="0.1.0",
    description="Config-driven FastAPI + LangGraph starter for reusable multi-agent workflows.",
)

app.add_api_route("/", workflow_editor, methods=["GET"], include_in_schema=False)
app.include_router(router)
