# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Config-driven FastAPI + LangGraph framework for reusable multi-agent workflows. Workflows are YAML-directed graphs; nodes are typed Python classes; models/tools/MCPs live behind adapters. Includes an embedded visual editor and SQLite run persistence.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# Run server (embedded editor at http://127.0.0.1:8000/)
./start.sh

# Dev mode with auto-reload
RELOAD=true ./start.sh

# Stop server
./stop.sh

# Status check
./status.sh

# Run all tests
pytest

# Run a single test file
pytest tests/test_mcp_tool.py

# Validate configs
python -m app.cli validate --config-dir configs

# Run a workflow via API
curl -X POST http://127.0.0.1:8000/workflows/starter_three_node/run \
  -H "Content-Type: application/json" -d '{"inputs":{}}'
```

## Architecture

**Two layers**: framework runtime (`app/`) and project configuration (`configs/`). Most changes start in configs; custom Python classes are added only when configs aren't enough.

**Execution flow**: API request → `ConfigLoader` loads workflow YAML → Pydantic validates as `WorkflowConfig` → `build_registries()` loads models/tools/MCPs → `GraphBuilder.compile()` creates a LangGraph `StateGraph` → nodes execute sequentially along edges → `RunStore` persists results.

**Shared state** (`app/core/state.py`): `WorkflowState` TypedDict with `inputs`, `artifacts`, `node_outputs`, `errors`, `logs`, `approvals`, `final_report`. Each node receives and returns updated state. Treat state as append/update-only.

**Three registries** (`app/core/registry.py`):
- `ModelRegistry` — maps provider types (`mock`, `openai`, `anthropic`, `ibm`, `local`) to factory functions
- `ToolRegistry` — maps tool types (`shell`, `tnt_cli`, `mcp`, `test_runner`, `repo_reader`) to factory functions
- `NodeRegistry` — maps node type strings to Python classes

**Node registration** (`app/core/graph_builder.py`): `default_node_registry()` maps YAML `type` values to node classes. New node types must be registered here.

## Key Conventions

- **New node type**: subclass `BaseNode`, implement `async def run(self, state) -> dict`, register in `default_node_registry()`, use type string in workflow YAML
- **New model provider**: subclass `ModelProvider`, implement `async def generate(...)`, register in `ModelRegistry._provider_type_factories`, add entry in `configs/models.yaml`
- **New tool**: subclass `Tool`, implement `async def run(...)`, register in `ToolRegistry._tool_type_factories`, add entry in `configs/tools.yaml`
- **MCP server**: add command to `configs/mcps.yaml`, expose as `type: mcp` tool in `configs/tools.yaml` with `config.server_id`, attach tool id to a node's `tools` list
- Nodes use `self.ask_model(...)` for model calls and `self.tools["tool_id"].run(...)` for tools — never import provider SDKs directly in node code
- API keys go in env vars, never in YAML
- Keep provider-specific code inside `app/models/` adapters; tool/MCP code inside `app/tools/` adapters

## Environment Variables

- `WORKFLOW_CONFIG_DIR` — override config directory (default: `./configs`)
- `WORKFLOW_RUN_STORE` — `sqlite` (default) or `memory`
- `WORKFLOW_RUN_DB` — SQLite path (default: `.runs/workflows.sqlite3`)
- `HOST` / `PORT` — server bind address (default: `127.0.0.1:8000`)
- `RELOAD` — set `true` for uvicorn auto-reload
- `RUN_FRONTEND` — `auto`/`true`/`false` for React Flow editor

## What's Mocked vs Real

**Real**: YAML validation, FastAPI routes, LangGraph execution, shared state, registries, SQLite persistence, MCP stdio path, visual editor save/load/run.

**Mocked/placeholder**: most node business logic, OpenAI/Anthropic provider adapters, `tnt-cli` reducer, human approval pause/resume, advanced React Flow editor.
