# Agentic Workflow Framework

A small starter framework for config-driven multi-agent workflows using FastAPI and LangGraph.

The project is intentionally generic: workflows are YAML graphs, nodes are typed Python classes, models live behind provider adapters, and tools/MCPs live behind tool adapters. The first included workflow is a mocked combinatorial test generation pipeline that can later call IBM `tnt-cli` to reduce test cases.

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
    combinatorial_test_generation.yaml
  models.yaml
  tools.yaml
app/
  main.py
  api/routes.py
  core/
    config_loader.py
    graph_builder.py1
    registry.py
    run_store.py
    state.py
  models/
  tools/
  nodes/
  schemas/
examples/
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

The editor loads `starter_three_node` first so you have a simple straight-line workflow to play with:

```text
doc_reader -> variable_extractor -> report_generator
```

The editor canvas supports dragging nodes horizontally across the grid, selecting nodes to edit their config, dragging from a node's right handle to another node's left handle to create an edge, selecting an edge on the canvas, and deleting the selected edge. Add nodes from the Node Palette on the left. Node positions are saved in each node's `config.ui` block when you save the workflow.

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

Run the example workflow:

```bash
curl -X POST http://127.0.0.1:8000/workflows/combinatorial_test_generation/run \
  -H "Content-Type: application/json" \
  -d @examples/sample_input.json
```

The API stores runs in memory. Use the returned `run_id` with:

```bash
curl http://127.0.0.1:8000/runs/<run_id>
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

1. Create a tool adapter in `app/tools`.
2. Subclass `Tool`.
3. Implement `async def run(...)`.
4. Register the tool type in `ToolRegistry`.
5. Add a tool entry in `configs/tools.yaml`.
6. Reference the tool id from a workflow node.

`ShellTool` is present but disabled by default and only allows explicitly configured commands. `TntCliTool` currently returns a mocked reduced test set and has a TODO where the real IBM `tnt-cli` invocation should go.

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

The tests validate config loading and compile/run the mocked LangGraph workflow.
