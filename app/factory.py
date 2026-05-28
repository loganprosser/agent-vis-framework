from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.api.routes import create_router
from app.core.config_loader import ConfigLoader
from app.core.run_store import create_run_store
from app.ui import workflow_editor


def create_app(config_dir: Path | str | None = None) -> FastAPI:
    app = FastAPI(
        title="Agentic Workflow Framework",
        version="0.1.0",
        description="Config-driven FastAPI + LangGraph runtime for reusable agentic workflows.",
    )
    app.add_api_route("/", workflow_editor, methods=["GET"], include_in_schema=False)
    app.include_router(create_router(ConfigLoader(config_dir), create_run_store()))
    return app
