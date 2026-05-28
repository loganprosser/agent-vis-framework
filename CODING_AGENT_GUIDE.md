# Coding Agent Guide

This document is written for a coding agent that is dropped into a copied project created from `agentic-workflow-framework`.

The goal of this repo is to provide a reusable n8n-style foundation for configurable agentic workflows:

- workflows are defined in YAML
- the backend is FastAPI
- execution is LangGraph
- nodes are typed Python classes
- models are behind provider adapters
- tools and MCP servers are behind tool adapters
- runs are persisted in SQLite by default
- the browser editor can load, edit, save, and run workflows

If you are a coding agent, read this file first, then inspect the files listed in the architecture map below.

## Quick Mental Model

The framework has two layers:

1. **Framework runtime**
   Code in `app/` knows how to load configs, validate them, build a LangGraph graph, execute nodes, call tools/MCPs, and expose FastAPI endpoints.

2. **Project configuration**
   Files in `configs/` define the actual workflows, model providers, tools, and MCP servers for a specific use case.

Most projects should start by changing configs, then add custom node/tool/model classes only when configs are not enough.

## Important Files

```text
app/main.py
  FastAPI entrypoint used by uvicorn.

app/factory.py
  App factory. Use create_app(config_dir=...) to embed this runtime with a different config folder.

app/api/routes.py
  FastAPI routes:
    GET  /health
    GET  /workflows
    GET  /workflows/{workflow_name}
    PUT  /workflows/{workflow_name}
    POST /workflows/validate
    POST /workflows/{workflow_name}/run
    GET  /runs/{run_id}

app/core/config_loader.py
  Loads YAML configs from WORKFLOW_CONFIG_DIR or ./configs.

app/core/graph_builder.py
  Converts WorkflowConfig into a LangGraph StateGraph.
  Registers built-in node types.

app/core/state.py
  Shared workflow state passed between nodes.

app/core/registry.py
  ModelRegistry, ToolRegistry, NodeRegistry.

app/core/run_store.py
  RunRecord, memory store, SQLite store, run-store factory.

app/schemas/workflow.py
  Pydantic schemas for workflows, models, tools, and MCP servers.

app/nodes/
  Node implementations. Add new node types here.

app/models/
  Model provider adapters. Add OpenAI/Anthropic/local/IBM adapters here.

app/tools/
  Tool adapters and MCP client/server demo.

app/ui.py
  Embedded no-build visual editor served at /.

frontend/
  Optional React/Vite/React Flow editor scaffold for a richer future UI.

configs/workflows/
  Project workflow YAML files.

configs/models.yaml
  Model provider definitions.

configs/tools.yaml
  Tool definitions exposed to nodes.

configs/mcps.yaml
  MCP server command/transport definitions.
```

## How To Run

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./start.sh
```

Open:

```text
http://127.0.0.1:8000/
```

Stop:

```bash
./stop.sh
```

Validate:

```bash
python -m app.cli validate --config-dir configs
pytest
```

## How To Create A New Project From This Framework

Preferred copy mode:

```bash
python -m app.cli init ../my-new-agent-project
```

Then:

```bash
cd ../my-new-agent-project
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
./start.sh
```

Alternative: reuse this checkout with another config folder:

```bash
WORKFLOW_CONFIG_DIR=/path/to/other-project/configs ./start.sh
```

## Workflow YAML Shape

A workflow is a directed graph:

```yaml
name: example_workflow
version: 0.1.0
description: Example workflow.
entrypoint: start_node

nodes:
  - id: start_node
    type: doc_reader
    provider: mock
    model: mock-deterministic
    system_prompt: Read the input document.
    input_keys:
      - requirements_doc
    output_keys:
      - documents
    tools: []
    retry_policy:
      max_attempts: 1
      backoff_seconds: 0
    human_approval: false
    config:
      ui:
        x: 140
        y: 260

edges:
  - source: start_node
    target: next_node
    label: documents
```

Node fields:

- `id`: unique node id in the workflow.
- `type`: maps to a Python class in `app/nodes/` via `default_node_registry`.
- `provider`: model provider id from `configs/models.yaml`.
- `model`: model name passed to the provider.
- `system_prompt`: node-level prompt.
- `input_keys`: values this node expects from inputs or prior outputs.
- `output_keys`: values this node promises to produce.
- `tools`: tool ids from `configs/tools.yaml`.
- `retry_policy`: basic retry metadata used by `BaseNode`.
- `human_approval`: currently records approval metadata; can later pause execution.
- `config`: freeform node config. `config.ui` stores visual editor coordinates.

Edge fields:

- `source`: upstream node id.
- `target`: downstream node id.
- `label`: visual/editor label only for now.

## Execution Flow

When `POST /workflows/{workflow_name}/run` is called:

1. `ConfigLoader` loads `configs/workflows/{workflow_name}.yaml`.
2. Pydantic validates it as `WorkflowConfig`.
3. `build_registries()` loads:
   - `configs/models.yaml`
   - `configs/tools.yaml`
   - `configs/mcps.yaml`
4. `GraphBuilder.compile()` creates a LangGraph `StateGraph`.
5. Each YAML node becomes a Python node object.
6. Each edge becomes a LangGraph edge.
7. The graph runs with initial shared state.
8. Each node updates `node_outputs`, `artifacts`, `logs`, `errors`, or `final_report`.
9. `RunStore` persists the run record.

## Shared State

Defined in `app/core/state.py`.

```python
WorkflowState = {
    "run_id": "...",
    "workflow_name": "...",
    "inputs": {},
    "artifacts": {},
    "node_outputs": {},
    "errors": [],
    "logs": [],
    "approvals": {},
    "final_report": None,
}
```

Nodes should treat this state as append/update-only. Avoid deleting data from other nodes unless the workflow explicitly owns that behavior.

## How To Add A New Node Type

1. Create a file in `app/nodes/`.

Example:

```python
from app.core.state import WorkflowState
from app.nodes.base import BaseNode


class RepoSummarizerNode(BaseNode):
    async def run(self, state: WorkflowState) -> dict:
        context = self.context(state)
        summary = await self.ask_model(state, "Summarize the repository inputs.")
        return {
            "repo_summary": summary,
            "input_keys_seen": sorted(context.keys()),
        }
```

2. Register it in `app/core/graph_builder.py`:

```python
from app.nodes.repo_summarizer import RepoSummarizerNode

registry.register("repo_summarizer", RepoSummarizerNode)
```

3. Use it in workflow YAML:

```yaml
- id: summarize_repo
  type: repo_summarizer
  provider: mock
  model: mock-deterministic
  system_prompt: Summarize the repository.
  input_keys: [source_reader]
  output_keys: [repo_summary]
  tools: []
```

Node guidance:

- Subclass `BaseNode`.
- Implement `async def run(self, state) -> dict`.
- Use `self.context(state)` to access inputs and prior outputs.
- Use `await self.ask_model(...)` for model calls.
- Use `await self.tools["tool_id"].run(...)` for tools/MCP.
- Return a dictionary; `BaseNode` stores it under `state["node_outputs"][node_id]`.

## How To Add A Model Provider

Provider config lives in `configs/models.yaml`:

```yaml
providers:
  - id: openai_default
    type: openai
    default_model: gpt-4.1-mini
    config:
      api_key_env: OPENAI_API_KEY
```

Provider adapter lives in `app/models/`.

Steps:

1. Create a class that subclasses `ModelProvider`.
2. Implement `async def generate(self, request: ModelRequest) -> ModelResponse`.
3. Register the provider type in `ModelRegistry`.
4. Reference the provider id from workflow nodes.

Keep all vendor-specific code inside provider adapters. Nodes should not import OpenAI, Anthropic, IBM, etc. directly.

## How To Add A Tool

Tool config lives in `configs/tools.yaml`:

```yaml
tools:
  - id: my_tool
    type: shell
    enabled: false
    config:
      allowed_commands: ["pytest"]
```

Tool adapter lives in `app/tools/`.

Steps:

1. Create a class that subclasses `Tool`.
2. Implement `async def run(self, **kwargs) -> ToolResult`.
3. Register the type in `ToolRegistry`.
4. Add the tool to `configs/tools.yaml`.
5. Add the tool id to a workflow node's `tools` list.

## How MCP Works

MCP is split into two config files:

```text
configs/mcps.yaml
  Defines MCP servers and how to start/connect to them.

configs/tools.yaml
  Exposes an MCP server as a tool id nodes can reference.
```

Example server:

```yaml
servers:
  - id: builtin_demo
    name: Built-in Demo MCP
    transport: stdio
    enabled: true
    command:
      - "{python}"
      - "-m"
      - "app.tools.example_mcp_server"
    cwd: "{project_root}"
    env: {}
    timeout_seconds: 10
```

Example tool exposure:

```yaml
tools:
  - id: builtin_demo_mcp
    type: mcp
    enabled: true
    config:
      server_id: builtin_demo
```

Example node:

```yaml
- id: discover_mcp_tools
  type: mcp_discovery
  provider: mock
  model: mock-deterministic
  input_keys: []
  output_keys: [mcp_tools]
  tools:
    - builtin_demo_mcp
```

The current MCP client supports stdio MCP:

- `initialize`
- `tools/list`
- `tools/call`

Files:

- `app/tools/mcp_client.py`
- `app/tools/mcp_tool.py`
- `app/tools/example_mcp_server.py`
- `app/nodes/mcp_discovery.py`

To add a real MCP server:

1. Add its command to `configs/mcps.yaml`.
2. Add a `type: mcp` entry to `configs/tools.yaml`.
3. Attach that tool id to a node.
4. Use `mcp_discovery_demo` as the reference workflow.

## How To Save Architectures

Architectures are saved as workflow YAML files:

```text
configs/workflows/<workflow_name>.yaml
```

The visual editor saves node coordinates in:

```yaml
config:
  ui:
    x: 140
    y: 260
```

Recommended pattern:

- one workflow YAML per major architecture
- use clear edge labels
- keep node ids stable
- prefer adding new node types over overloading one generic node with too many modes
- keep project-specific prompts in workflow YAML initially
- move repeated behavior into Python node classes once it appears in multiple workflows

## Recommended Project Structure For A New Use Case

```text
my-agent-project/
  configs/
    workflows/
      repo_test_generation.yaml
      support_triage.yaml
    models.yaml
    tools.yaml
    mcps.yaml
  app/
    nodes/
      repo_summarizer.py
      issue_classifier.py
    tools/
      custom_internal_api_tool.py
  tests/
  README.md
```

## What Is Real vs Placeholder

Real:

- YAML validation
- FastAPI routes
- LangGraph graph compilation/execution
- shared state object
- model/tool registries
- SQLite run persistence
- MCP stdio initialize/list/call path
- visual editor save/load/run path

Placeholder/mock:

- most workflow node business logic
- OpenAI/Anthropic provider adapters
- IBM `tnt-cli` reducer implementation
- human approval pause/resume
- advanced editor validation and rich React Flow UI

## Testing Expectations

Run:

```bash
pytest
python -m app.cli validate --config-dir configs
```

Useful targeted tests:

```bash
pytest tests/test_mcp_tool.py
pytest tests/test_run_store.py
```

Before changing graph execution, run all tests.

## Common Coding-Agent Tasks

### Create A New Workflow

1. Copy `configs/workflows/starter_three_node.yaml`.
2. Rename `name`.
3. Edit `nodes` and `edges`.
4. Validate:

```bash
python -m app.cli validate --config-dir configs
```

5. Open editor and run.

### Add A Real MCP To A Workflow

1. Add MCP server in `configs/mcps.yaml`.
2. Add MCP tool exposure in `configs/tools.yaml`.
3. Add the tool id to a node's `tools`.
4. Use `mcp_discovery` first to confirm the server returns tools.
5. Add or update a custom node to call the specific MCP tool.

### Add A New Real LLM Provider

1. Implement adapter in `app/models/`.
2. Register it in `ModelRegistry`.
3. Add config to `configs/models.yaml`.
4. Set node `provider` and `model`.
5. Keep keys in env vars, not YAML.

### Persist Or Inspect Runs

Default DB:

```text
.runs/workflows.sqlite3
```

Environment variables:

```bash
WORKFLOW_RUN_STORE=sqlite
WORKFLOW_RUN_DB=.runs/workflows.sqlite3
```

For throwaway memory mode:

```bash
WORKFLOW_RUN_STORE=memory ./start.sh
```

## Design Rules For Future Work

- Keep provider-specific code behind `app/models/` adapters.
- Keep tool/MCP-specific code behind `app/tools/` adapters.
- Keep node logic focused on workflow semantics.
- Keep workflows declarative in YAML.
- Do not hardcode project-specific behavior in `GraphBuilder`.
- Register new node types explicitly.
- Prefer Pydantic validation for new config shapes.
- Keep the embedded editor dependency-free unless intentionally moving to `frontend/`.
- Use React Flow in `frontend/` for richer graph editing when Node/npm are available.

