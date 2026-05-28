# Agentic Workflow Framework

A small starter framework for config-driven multi-agent workflows using FastAPI and LangGraph.

The project is intentionally generic: workflows are YAML graphs, nodes are typed Python classes, models live behind provider adapters, and tools/MCPs live behind tool adapters. It includes a visual editor, SQLite run persistence, a tiny working MCP stdio demo server, and a mocked combinatorial test generation pipeline that can later call IBM `tnt-cli`.

## Architecture

At runtime the API loads a workflow YAML file from `configs/workflows`, validates it with Pydantic, creates model and tool adapters from `configs/models.yaml` and `configs/tools.yaml`, then compiles the workflow into a LangGraph `StateGraph`.

The shared state is defined in `app/core/state.py` and carries:

- `inputs`
- `artifacts`
- `node_outputs`
- `errors`
- `logs`
- `approvals`
- `final_report`

Each node receives the same state object and returns an updated state. The starter nodes return deterministic mocked outputs so the app runs without API keys.

## Project Layout

```text
configs/
  workflows/
    starter_three_node.yaml
    mcp_discovery_demo.yaml
    combinatorial_test_generation.yaml
  models.yaml
  mcps.yaml
  tools.yaml
app/
  main.py
  api/routes.py
  ui.py
  core/
    config_loader.py
    graph_builder.py
    registry.py
    run_store.py
    state.py
  models/
  tools/
  nodes/
  schemas/
examples/
frontend/
tests/
```

## Run Locally

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Start the API and visual editor:

```bash
./start.sh
```

For development auto-reload:

```bash
RELOAD=true ./start.sh
```

Then open:

```text
http://127.0.0.1:8000/
```

If Node/npm are installed, `./start.sh` also starts the optional React Flow editor:

```text
http://127.0.0.1:5173/
```

The embedded FastAPI editor at port `8000` remains available even without Node.

The editor loads `starter_three_node` first so you have a simple straight-line workflow to play with:

```text
doc_reader -> variable_extractor -> report_generator
```

The editor canvas supports zoom (Ctrl/Cmd + scroll, or the +/−/Fit buttons), panning by dragging the canvas, dragging nodes to reposition them, selecting nodes to edit their config, and dragging from a node's right handle to another node's left handle to create an edge. The canvas auto-sizes to fit all nodes. The Fit button zooms to show the entire workflow in the viewport.

The right panel shows the selected node's configuration with dropdown selectors for provider and model (populated from `configs/models.yaml`), and separate chip-based selectors for Tools and MCPs (populated from `configs/tools.yaml`). Selected items appear as removable chips — teal for tools, purple for MCPs — with a dropdown to add more. All delete actions require confirmation.

Stop it:

```bash
./stop.sh
```

Check status:

```bash
./status.sh
```

Check health:

```bash
curl http://127.0.0.1:8000/health
```

## Use As A Template For Another Project

You can use this repo as a reusable starter for a new n8n-style agent workflow project.

### macOS Setup

Assuming Xcode Command Line Tools and Homebrew are already installed:

```bash
brew install python git
```

Optional, only needed for the future React Flow frontend:

```bash
brew install node
```

### Create A New Repo From The Framework

Clone this framework repo somewhere on your machine:

```bash
git clone <THIS_FRAMEWORK_REPO_URL> agentic-workflow-framework
cd agentic-workflow-framework
```

Create a new self-contained project folder:

```bash
python3 -m app.cli init ../my-agent-workflow
```

That command physically copies the framework into `../my-agent-workflow`, including:

- `app/`
- `configs/`
- `frontend/`
- `tests/`
- scripts like `start.sh` and `stop.sh`
- docs like `README.md` and `CODING_AGENT_GUIDE.md`

Now move into the copied project and run it:

```bash
cd ../my-agent-workflow
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
./start.sh
```

The virtualenv does not copy the project. The copy already happened during `python3 -m app.cli init ...`. The virtualenv just installs the copied project locally so Python can run FastAPI, LangGraph, tests, and the CLI.

Open:

```text
http://127.0.0.1:8000/
```

Turn the copied folder into its own Git repo:

```bash
git init
git add .
git commit -m "Initial agentic workflow project"
```

If you already created an empty remote repo on GitHub/GitLab/etc.:

```bash
git remote add origin <YOUR_NEW_REPO_URL>
git branch -M main
git push -u origin main
```

For a project that only wants different configs while reusing this checkout's runtime:

```bash
WORKFLOW_CONFIG_DIR=/path/to/other-project/configs ./start.sh
```

The reusable framework code is in `app/`. The project-specific surface is mostly:

- `configs/workflows/*.yaml`
- `configs/models.yaml`
- `configs/tools.yaml`
- `configs/mcps.yaml`
- custom node classes in `app/nodes/`
- custom model/tool adapters in `app/models/` and `app/tools/`

Programmatic embedding is also supported:

```python
from app.factory import create_app

app = create_app(config_dir="configs")
```

Run the example workflow:

```bash
curl -X POST http://127.0.0.1:8000/workflows/combinatorial_test_generation/run \
  -H "Content-Type: application/json" \
  -d @examples/sample_input.json
```

The API stores runs in SQLite by default at `.runs/workflows.sqlite3`. Use the returned `run_id` with:

```bash
curl http://127.0.0.1:8000/runs/<run_id>
```

The `/catalog` endpoint returns available providers, tools, and MCPs (used by the visual editor to populate dropdowns):

```bash
curl http://127.0.0.1:8000/catalog
```

## Workflow Configs

A workflow YAML file describes a directed graph:

```yaml
name: my_workflow
entrypoint: first_node
nodes:
  - id: first_node
    type: doc_reader
    provider: mock
    model: mock-deterministic
    system_prompt: Summarize relevant docs.
    input_keys: [requirements_doc]
    output_keys: [documents]
    tools: [filesystem_mcp]
    retry_policy:
      max_attempts: 1
      backoff_seconds: 0
    human_approval: false
edges:
  - source: first_node
    target: second_node
    label: documents
```

Validation lives in `app/schemas/workflow.py`.

## Add A New Node Type

1. Create a node class in `app/nodes/your_node.py`.
2. Subclass `BaseNode`.
3. Implement `async def run(self, state) -> dict`.
4. Register the type in `default_node_registry()` in `app/core/graph_builder.py`.
5. Use the new `type` in workflow YAML.

Nodes should use `self.ask_model(...)` for model calls and `self.tools["tool_id"].run(...)` for tools. This keeps provider and MCP details out of node logic.

## Add A New Model Provider

1. Create a provider adapter in `app/models`.
2. Subclass `ModelProvider`.
3. Implement `async def generate(...)`.
4. Register the provider type in `ModelRegistry` in `app/core/registry.py`.
5. Add a provider entry in `configs/models.yaml`.

Provider-specific SDKs, auth, retries, request formatting, and response parsing should stay inside the adapter.

## Add A New Tool Or MCP

For a normal tool:

1. Create a tool adapter in `app/tools`.
2. Subclass `Tool`.
3. Implement `async def run(...)`.
4. Register the tool type in `ToolRegistry`.
5. Add a tool entry in `configs/tools.yaml`.
6. Reference the tool id from a workflow node.

For an MCP server:

1. Add the server command to `configs/mcps.yaml`.
2. Expose it as a tool in `configs/tools.yaml` with `type: mcp` and `config.server_id`.
3. Add that tool id to a node's `tools` list.
4. Use `mcp_discovery` to list available tools or call the MCP from a custom node.

Example:

```yaml
# configs/mcps.yaml
servers:
  - id: builtin_demo
    name: Built-in Demo MCP
    transport: stdio
    enabled: true
    command: ["{python}", "-m", "app.tools.example_mcp_server"]
    cwd: "{project_root}"
```

```yaml
# configs/tools.yaml
tools:
  - id: builtin_demo_mcp
    type: mcp
    enabled: true
    config:
      server_id: builtin_demo
```

```yaml
# workflow node
tools:
  - builtin_demo_mcp
```

`ShellTool` is present but disabled by default and only allows explicitly configured commands. `McpTool` now supports stdio MCP `initialize`, `tools/list`, and `tools/call`. `TntCliTool` currently returns a mocked reduced test set and has a TODO where the real IBM `tnt-cli` invocation should go.

## MCP Demo

Run the built-in MCP discovery workflow:

```bash
curl -X POST http://127.0.0.1:8000/workflows/mcp_discovery_demo/run \
  -H "Content-Type: application/json" \
  -d '{"inputs":{}}'
```

It starts `app.tools.example_mcp_server` over stdio, lists its tools, and writes the result into workflow state.

## Run Persistence

By default:

```text
WORKFLOW_RUN_STORE=sqlite
WORKFLOW_RUN_DB=.runs/workflows.sqlite3
```

For temporary memory-only runs:

```bash
WORKFLOW_RUN_STORE=memory ./start.sh
```

## Example Workflow

`configs/workflows/combinatorial_test_generation.yaml` runs:

```text
doc_reader -> source_reader -> variable_extractor -> variable_classifier
-> domain_generator -> constraint_builder -> tnt_cli_reducer -> test_writer
-> test_validator -> test_runner -> report_generator
```

The final report summarizes extracted variables, generated domains, constraints, reduced test set, generated tests, validation findings, and run results.

## Tests

```bash
pytest
```

The tests validate config loading, graph execution, SQLite run persistence, and the built-in MCP stdio path.
