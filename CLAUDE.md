# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Config-driven FastAPI + LangGraph framework for reusable multi-agent workflows. Workflows are YAML-directed graphs; nodes are typed Python classes; models/tools/MCPs live behind adapters. Includes an embedded visual editor with markdown prompt editing and SQLite run persistence.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# With LiteLLM/OpenAI support
pip install -e ".[dev,litellm]"

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

**Execution flow**: API request → `ConfigLoader` loads workflow YAML → Pydantic validates as `WorkflowConfig` → `build_registries()` loads models/tools/MCPs → `GraphBuilder.compile()` creates LangGraph `StateGraph` → nodes execute along edges → `RunStore` persists results.

**Shared state** (`app/core/state.py`): `WorkflowState` TypedDict with `inputs`, `artifacts`, `node_outputs`, `errors`, `logs`, `approvals`, `final_report`. Each node receives and returns updated state. Treat state as append/update-only.

**Three registries** (`app/core/registry.py`):
- `ModelRegistry` — maps provider types (`mock`, `openai`, `anthropic`, `ibm`, `litellm`, `local`) to factory functions
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

## Markdown Prompt Files

Nodes can reference prompt content from `.md` files instead of inline `system_prompt` text. Set `system_prompt_file` on a node to a path relative to `configs/prompts/`.

```yaml
# In a workflow node:
system_prompt: Fallback text if file is missing
system_prompt_file: doc_reader.md
```

The file is resolved as `configs/prompts/<system_prompt_file>`. At graph compilation time, `GraphBuilder` loads the file content and replaces `system_prompt` with the resolved text. If the file is missing, the inline `system_prompt` is used as a fallback.

**API endpoints**:
- `GET /prompts` — list all `.md` files in `configs/prompts/`
- `GET /prompts/{path}` — read a prompt file
- `PUT /prompts/{path}` — create or update a prompt file (body: `{"content": "..."}`)
- `DELETE /prompts/{path}` — delete a prompt file

**Visual editor**: The "Prompt File" field in the node editor accepts a path like `prompts/my_node.md`. The "Edit in MD Editor" button opens a split-pane markdown editor with live preview (uses marked.js from CDN). Saving writes to the `configs/prompts/` directory via the API.

**Path traversal protection**: `_resolve_prompt_path()` validates that resolved paths stay within `configs/prompts/`.

## McpCallNode

A generic node type (`mcp_call`) for calling a specific MCP tool by name. Config-driven — no custom Python needed.

```yaml
# In a workflow node:
type: mcp_call
tools: [my_mcp_tool]
config:
  mcp_tool_name: calculate_coverage
  arguments:
    parameters: "{extract_variables.result}"
```

**Argument resolution**: String values wrapped in `{...}` are resolved from prior node outputs using `{node_id.key}` dot-notation paths. Non-string values pass through unchanged.

## LiteLLM / OpenAI Provider

The `openai` and `litellm` provider types use `OpenAIModelProvider`, which connects to any OpenAI-compatible API (direct OpenAI, LiteLLM proxy, IBM RITS, etc.).

```yaml
# In configs/models.yaml:
providers:
  - id: my_litellm
    type: litellm
    default_model: GLM-5.1-FP8
    config:
      api_key_env: LITELLM_API_KEY
      temperature: 0
```

**Config keys**:
- `base_url` — API base URL (default: `LITELLM_BASE_URL` env var or `http://localhost:4002/v1`)
- `api_key_env` — env var name for the API key (default: `OPENAI_API_KEY`, falls back to `LITELLM_API_KEY`)
- `temperature` — sampling temperature (default: 0)

Requires `pip install openai` or `pip install -e ".[litellm]"`. The `openai` package is imported lazily on first use — if missing, the provider raises `RuntimeError` with install instructions.

## MCP Dual-Transport Support

The MCP client (`StdioMcpClient`) auto-detects whether the server uses Content-Length framed or NDJSON transport. It sends in NDJSON format (compatible with the official TypeScript MCP SDK) and detects the server's format on the first response.

The built-in demo MCP server (`example_mcp_server.py`) also supports both formats — it reads either format and sends NDJSON.

**Environment variable expansion**: Server commands in `configs/mcps.yaml` support `{env:VAR_NAME}` syntax (e.g., `{env:TESTFORGE_REPO_DIR}`). Missing env vars produce an empty string, which triggers a clear error message at startup.

**Error handling**: `McpTool` checks for `isError: true` in MCP responses and returns a `ToolResult` with `ok=False` and the error text from the response content.

## Environment Variables

- `WORKFLOW_CONFIG_DIR` — override config directory (default: `./configs`)
- `WORKFLOW_RUN_STORE` — `sqlite` (default) or `memory`
- `WORKFLOW_RUN_DB` — SQLite path (default: `.runs/workflows.sqlite3`)
- `HOST` / `PORT` — server bind address (default: `127.0.0.1:8000`)
- `RELOAD` — set `true` for uvicorn auto-reload
- `RUN_FRONTEND` — `auto`/`true`/`false` for React Flow editor
- `LITELLM_BASE_URL` — default base URL for litellm/openai providers
- `LITELLM_API_KEY` — fallback API key for litellm/openai providers

## What's Mocked vs Real

**Real**: YAML validation, FastAPI routes, LangGraph execution, shared state, registries, SQLite persistence, MCP stdio path (dual-transport), visual editor save/load/run, markdown prompt files, prompt API endpoints, OpenAI/LiteLLM provider, McpCallNode, MCP error detection.

**Mocked/placeholder**: Anthropic provider adapter, human approval pause/resume, advanced React Flow editor.
