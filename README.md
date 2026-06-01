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
./configure.sh
./start.sh
```

`./configure.sh` prompts for the persisted bind host, FastAPI backend port, and React control-plane port. It writes the ignored local file `.runtime.env`, which is read by `./start.sh` and `./status.sh`.

For development auto-reload:

```bash
RELOAD=true ./start.sh
```

Then open:

```text
http://127.0.0.1:5173/
```

If Node/npm are installed, `./start.sh` starts the React Flow control plane:

```text
http://127.0.0.1:5173/
```

The embedded FastAPI editor at `http://127.0.0.1:8000/` remains as a no-build fallback while its useful controls move into the React studio.

The editor loads `starter_three_node` first so you have a simple straight-line workflow to play with:

```text
doc_reader -> variable_extractor -> report_generator
```

The editor canvas supports zoom (Ctrl/Cmd + scroll, or the +/−/Fit buttons), panning by dragging the canvas, dragging nodes to reposition them, selecting nodes to edit their config, and dragging from a node's right handle to another node's left handle to create an edge. The canvas auto-sizes to fit all nodes. The Fit button zooms to show the entire workflow in the viewport.

The right panel shows the selected node's configuration with dropdown selectors for provider and model (populated from `configs/models.yaml`), and separate chip-based selectors for Tools and MCPs (populated from `configs/tools.yaml`). Selected items appear as removable chips — teal for tools, purple for MCPs — with a dropdown to add more. All delete actions require confirmation.

The React Flow control plane at port `5173` is the primary editor. It edits workflow metadata, graph edges, common node contracts, providers, models, tools, MCP-backed tools, retry settings, Markdown prompt files, generic node config JSON, Burr subsystem factory contracts, Burr visualization topology, and runtime traces.

Markdown prompt files live beneath `configs/prompts/`. For agent-authored projects, keep them nested by workflow and node:

```text
configs/prompts/workflows/<workflow>/nodes/<node>.md
configs/prompts/workflows/<workflow>/subsystems/<subsystem>/actions/<action>.md
```

Normal node `system_prompt_file` references are loaded by the runtime. Burr action `prompt_file` references are visualization metadata until the Python Burr factory explicitly loads them; the editor labels that boundary clearly.

Stop it:

```bash
./stop.sh
```

Check status:

```bash
./status.sh
```

If another project already uses port `5173`, choose another frontend port:

```bash
./configure.sh --frontend-port 5174
./start.sh
```

`./stop.sh` stops both managed services.

## Configure A Local Ollama Model

The runtime keeps model calls behind the provider-neutral `ModelProvider` interface. Ollama has a native adapter in `app/models/ollama_provider.py`; nodes do not contain Ollama-specific code.

Install and start Ollama, pull at least one model, and install `fzf`:

```bash
brew install ollama fzf
ollama serve
ollama pull qwen2.5-coder:7b
```

Configure a provider:

```bash
./configure-model.sh
```

The script uses `fzf` to select:

1. Provider type. The first supported local provider is `ollama`.
2. An installed model returned by the local Ollama server.
3. The model context window.

It adds or updates `ollama_local` in `configs/models.yaml` without removing other providers. Select `ollama_local` on workflow nodes in the React control plane, or set it directly in YAML:

```yaml
provider: ollama_local
model: qwen2.5-coder:7b
```

Leave `model` empty or set it to `~` (null) to use the provider's `default_model`:

```yaml
provider: ollama_local
model: ~
```

Check health:

```bash
curl http://127.0.0.1:8000/health
```

## Model Providers

All model calls go through the provider-neutral `ModelProvider` interface. Nodes call `self.ask_model(...)` and never import provider SDKs directly. Providers are defined in `configs/models.yaml` and registered in `app/core/registry.py`.

### Available Provider Types

| Type | Adapter | Status | Config Keys |
|------|---------|--------|-------------|
| `mock` | `MockModelProvider` | Real | `temperature` |
| `ollama` | `OllamaModelProvider` | Real | `base_url`, `context_length`, `temperature`, `timeout_seconds` |
| `openai` | `OpenAIModelProvider` | Real | `base_url`, `api_key_env`, `temperature` |
| `litellm` | `OpenAIModelProvider` | Real | `base_url`, `api_key_env`, `temperature` |
| `anthropic` | `AnthropicModelProvider` | Placeholder | `api_key_env` |
| `ibm` | `OpenAIModelProvider` | Real | `base_url`, `api_key_env`, `temperature` |
| `local` | `MockModelProvider` | Real | `temperature` |

The `openai` and `litellm` types both use `OpenAIModelProvider` with lazy SDK imports. The `ibm` type reuses it for RITS-compatible endpoints.

### Provider Selection In The Editor

The right panel inspector shows a **Provider** dropdown populated from `configs/models.yaml`. Each option shows `provider_id (type)`. Changing the provider auto-fills the **Model** field with that provider's `default_model`. Override it by typing a different model name, or leave it as-is.

### Provider Config In YAML

```yaml
# configs/models.yaml
providers:
  - id: ollama_local
    type: ollama
    default_model: ibm/granite4.1:8b-q8_0
    config:
      base_url: http://127.0.0.1:11434
      context_length: 16384
      temperature: 0
      timeout_seconds: 120

  - id: openai_default
    type: openai
    default_model: gpt-4.1-mini
    config:
      api_key_env: OPENAI_API_KEY

  - id: litellm_proxy
    type: litellm
    default_model: claude-sonnet-4-6
    config:
      base_url: https://my-litellm-proxy.example.com
      api_key_env: LITELLM_API_KEY
```

API keys always go in environment variables (referenced by `api_key_env`), never in YAML.

### Assigning Providers To Nodes

In workflow YAML, set `provider` and optionally `model`:

```yaml
- id: my_node
  type: doc_reader
  provider: ollama_local
  model: ~                    # use the provider's default_model
```

Or select them from the dropdowns in the visual editor.

### Burr Subsystem Model Passthrough

`burr_subsystem` nodes automatically forward their `provider` and `model` configuration to the Burr factory function. When the provider is `ollama`, the node injects `ollama_model` and `ollama_base_url` kwargs into the factory call. This means Burr subsystems use the same model from `configs/models.yaml` without needing a separate `OLLAMA_MODEL` environment variable.

The factory function must accept these kwargs:

```python
def build_my_app(problem_spec: str, *, ollama_model: str | None = None, ollama_base_url: str | None = None):
    model = ollama_model or os.environ.get("OLLAMA_MODEL", "llama3.2")
    base_url = ollama_base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ...
```

## Running Workflows From The Visual Editor

The left panel has a **Run Inputs** section with three input modes:

1. **Fields** (default) — auto-generates an input field for each key from the workflow's entrypoint node `input_keys`. Just type your values and click Run.

2. **Paste curl** — paste a full `curl -X POST ...` command and click **Parse & Fill**. It extracts the JSON body and fills the structured input fields.

3. **Raw JSON** — type or paste the full `{"inputs": {...}}` request body directly.

After a run completes, the left panel shows the run status and ID. The **Runtime Timeline** below shows every event. Select a node in the canvas to see its output in the right panel's expandable sections:

- **Node Output** — the full JSON output from that node
- **Runtime Artifacts** (burr_subsystem) — download links for trace and state files
- **Burr Action Sequence** (burr_subsystem) — the draft/critique/evaluate loop
- **Burr Action Events** (burr_subsystem) — per-action timing and status
- **Subsystem Metadata** (burr_subsystem) — duration, halt reason, terminal state

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
- scripts like `start.sh`, `stop.sh`, `configure.sh`, and `configure-model.sh`
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

Runtime visualizers can poll the ordered event stream for the same run:

```bash
curl http://127.0.0.1:8000/runs/<run_id>/events
```

Events cover parent node lifecycle, tool and MCP activity, Burr subsystem lifecycle, and internal Burr actions. Burr builder factories are instrumented through Burr's public `ApplicationBuilder.with_hooks(...)` API.

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
3. Implement `async def run(self, state) -> dict` for a simple node, or override `async def execute(self, context) -> NodeResult` for the typed plugin interface.
4. Register the type in `default_node_registry()` in `app/core/graph_builder.py`.
5. Use the new `type` in workflow YAML.

Nodes should use `self.ask_model(...)` for model calls and `self.tools["tool_id"].run(...)` for tools. This keeps provider and MCP details out of node logic.

## Run A Burr Subsystem

Use `burr_subsystem` when one workflow node should run an internal Burr application:

```yaml
- id: greet_with_burr
  type: burr_subsystem
  input_keys: [message]
  output_keys: [greeting]
  config:
    app_module: app.subsystems.example_burr_app
    app_factory: build_example_app
    input_map:
      message: inputs.message
    output_map:
      greeting: greeting
    halt_after: [greet]
    artifact_name: burr_final_state
    timeout_seconds: 30
    fail_on_error: true
    topology:
      entrypoint: greet
      actions:
        - id: greet
          label: Create greeting
          kind: agent
          reads: [message]
          writes: [greeting]
      transitions: []
```

The configured factory may return a Burr `ApplicationBuilder` or a built application. Set exactly one of `halt_after` or `terminal_states`; use `terminal_states` when the child application should stop after its state `status` reaches one of the configured values. The selected outputs become the node output. Each run stores `burr_final_state.json`, `burr_node_metadata.json`, and `burr_trace.json` in the node artifact bundle. For factories that return an `ApplicationBuilder`, the adapter attaches a Burr lifecycle hook and records action-level start/end events, results, errors, timings, and state snapshots in `burr_trace.json`. Built applications still run, but expose the minimal subsystem start/end trace because Burr hooks must be attached before build time. The configured `artifact_name`, which defaults to `burr_final_state`, remains as a convenient state alias. `timeout_seconds` is optional and `fail_on_error` defaults to `true`. Burr config is validated when the workflow loads.

`topology` is optional declarative editor metadata inspired by Burr's telemetry application model: an entrypoint, internal actions, and conditional transitions. It is validated and saved with workflow YAML, but the Python factory remains the runtime source of truth. This gives the editor a stable authoring model now and a natural place to attach richer Burr runtime telemetry later.

See `configs/workflows/branching_burr_requirements.yaml` for a small Burr subsystem that validates requirements and conditionally routes through an internal repair action.

## Add A New Model Provider

1. Create a provider adapter in `app/models/your_provider.py`.
2. Subclass `ModelProvider` and implement `async def generate(self, request: ModelRequest) -> ModelResponse`:

```python
from app.models.base import ModelProvider, ModelRequest, ModelResponse


class YourProvider(ModelProvider):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self.default_model
        # Call your API here, using self.config for base_url, api_key, etc.
        text = "response from your API"
        return ModelResponse(text=text, raw={"provider": self.provider_id, "model": model})
```

3. Register the provider type in `ModelRegistry._provider_type_factories` in `app/core/registry.py`:

```python
from app.models.your_provider import YourProvider

class ModelRegistry:
    _provider_type_factories = {
        ...
        "your_type": lambda id, model, config: YourProvider(id, model, config),
    }
```

4. Add a provider entry in `configs/models.yaml`:

```yaml
providers:
  - id: your_provider
    type: your_type
    default_model: your-model-name
    config:
      base_url: https://api.example.com
      api_key_env: YOUR_API_KEY
      temperature: 0.7
```

5. Use it in workflow YAML or select it from the Provider dropdown in the editor.

Provider-specific SDKs, auth, retries, request formatting, and response parsing should stay inside the adapter. Nodes must not import provider SDKs directly.

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
