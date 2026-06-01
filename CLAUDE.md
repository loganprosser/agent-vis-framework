# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Config-driven FastAPI + LangGraph framework for reusable multi-agent workflows. Workflows are YAML-directed graphs; nodes are typed Python classes; models/tools/MCPs live behind adapters. Includes a React control plane (Vite/React Flow at port 5173), a no-build fallback editor (port 8000), Markdown prompt editing, and SQLite run persistence.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# With LiteLLM/OpenAI support
pip install -e ".[dev,litellm]"

# Run backend and React control plane (primary UI at http://127.0.0.1:5173/)
./configure.sh        # prompts for bind host, backend port, frontend port → writes .runtime.env
./start.sh

# Add or update a local Ollama provider with fzf
./configure-model.sh

# Dev mode with auto-reload
RELOAD=true ./start.sh

./stop.sh          # stop both services
./status.sh        # check running services

# Tests
pytest
pytest tests/test_mcp_tool.py    # single file
pytest tests/test_run_store.py

# Validate configs
python -m app.cli validate --config-dir configs

# Run a workflow via API
curl -X POST http://127.0.0.1:8000/workflows/starter_three_node/run \
  -H "Content-Type: application/json" -d '{"inputs":{}}'
```

## Architecture

**Two layers**: framework runtime (`app/`) and project configuration (`configs/`). Most changes start in configs; custom Python classes are added only when configs aren't enough.

**Execution flow**: API request → `ConfigLoader` loads workflow YAML → Pydantic validates as `WorkflowConfig` → `build_registries()` loads models/tools/MCPs → `GraphBuilder.compile()` creates LangGraph `StateGraph` → nodes execute along edges → `RunStore` persists results.

**Shared state** (`app/core/state.py`): `WorkflowState` TypedDict with `inputs`, `artifacts`, `node_outputs`, `errors`, `logs`, `approvals`, `final_report`. Each node receives and returns updated state. Treat state as append/update-only.

**Three registries** (`app/core/registry.py`):
- `ModelRegistry` — maps provider types (`mock`, `openai`, `anthropic`, `ibm`, `litellm`, `local`) to factory functions
- `ToolRegistry` — maps tool types (`shell`, `tnt_cli`, `mcp`, `test_runner`, `repo_reader`) to factory functions
- `NodeRegistry` — maps node type strings to Python classes

**Node registration** (`app/core/graph_builder.py`): `default_node_registry()` maps YAML `type` values to node classes. New node types must be registered here.

**Frontend** (`frontend/`): React 19 + Vite + ReactFlow. Source files in `frontend/src/` — `main.tsx` (entry), `editor-panels.tsx` (panels), `types.ts` (TypeScript types). Run via `npm run dev` inside `frontend/` or automatically through `./start.sh`.

## Key Conventions

- **New node type**: subclass `BaseNode`, implement `async def run(self, state) -> dict`, register in `default_node_registry()`, use type string in workflow YAML
- **New model provider**: subclass `ModelProvider`, implement `async def generate(...)`, register in `ModelRegistry._provider_type_factories`, add entry in `configs/models.yaml`
- **New tool**: subclass `Tool`, implement `async def run(...)`, register in `ToolRegistry._tool_type_factories`, add entry in `configs/tools.yaml`
- **MCP server**: add command to `configs/mcps.yaml`, expose as `type: mcp` tool in `configs/tools.yaml` with `config.server_id`, attach tool id to a node's `tools` list
- Nodes use `self.ask_model(...)` for model calls and `self.tools["tool_id"].run(...)` for tools — never import provider SDKs directly in node code
- Keep provider-specific code inside `app/models/` adapters; tool/MCP code inside `app/tools/` adapters
- API keys go in env vars, not YAML

## Markdown Prompt Files

Nodes can reference `.md` files instead of inline `system_prompt`. Set `system_prompt_file` on a node to a path relative to `configs/prompts/`. `GraphBuilder` loads the file at compile time; missing files fall back to inline `system_prompt`.

Prefer nested layout:
```text
configs/prompts/workflows/<workflow>/nodes/<node>.md
configs/prompts/workflows/<workflow>/subsystems/<subsystem>/actions/<action>.md
```

Prompt API: `GET/PUT/DELETE /prompts/{path}`, `GET /prompts`.

Burr topology action `prompt_file` references are visualization metadata only — the Python Burr factory must explicitly load them.

## Burr Subsystem Nodes

Use `type: burr_subsystem` when a workflow node should run an internal Burr application. The `config.app_module` / `config.app_factory` points to a Python factory returning a Burr `ApplicationBuilder` or built application. Set exactly one of `halt_after` or `terminal_states`.

The optional `topology` block is declarative editor metadata (entrypoint, actions, transitions); the Python factory is the runtime source of truth.

Artifacts: `burr_final_state.json`, `burr_node_metadata.json`, `burr_trace.json`. Factories returning `ApplicationBuilder` get full action-level trace via Burr hooks; pre-built applications get minimal subsystem-level trace.

See `configs/workflows/branching_burr_requirements.yaml` for a working example.

## McpCallNode

Generic node type (`mcp_call`) for calling a specific MCP tool by name — no custom Python needed. String values wrapped in `{node_id.key}` in `config.arguments` are resolved from prior node outputs.

## LiteLLM / OpenAI Provider

Both `openai` and `litellm` types use `OpenAIModelProvider`. Requires `pip install openai` or `pip install -e ".[litellm]"` (imported lazily). Config keys: `base_url`, `api_key_env`, `temperature`. Defaults to `LITELLM_BASE_URL` / `LITELLM_API_KEY` env vars.

## MCP Transport

`StdioMcpClient` auto-detects Content-Length framed vs NDJSON transport. Server commands in `configs/mcps.yaml` support `{env:VAR_NAME}` expansion and `{python}` / `{project_root}` placeholders.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `WORKFLOW_CONFIG_DIR` | `./configs` | Config directory override |
| `WORKFLOW_RUN_STORE` | `sqlite` | `sqlite` or `memory` |
| `WORKFLOW_RUN_DB` | `.runs/workflows.sqlite3` | SQLite path |
| `HOST` / `PORT` | `127.0.0.1:8000` | Server bind |
| `RELOAD` | — | `true` for uvicorn auto-reload |
| `RUN_FRONTEND` | `auto` | `auto`/`true`/`false` |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Native Ollama API |
| `LITELLM_BASE_URL` | — | Default base URL for litellm/openai |
| `LITELLM_API_KEY` | — | Fallback API key for litellm/openai |

## What's Real vs Mocked

**Real**: YAML validation, FastAPI routes, LangGraph execution, shared state, registries, SQLite persistence, MCP stdio (dual-transport), visual editor save/load/run, markdown prompt API, native Ollama provider, OpenAI/LiteLLM provider, McpCallNode, Burr subsystem lifecycle + tracing.

**Mocked/placeholder**: Anthropic provider adapter, human approval pause/resume, IBM `tnt-cli` reducer, most workflow node business logic.
