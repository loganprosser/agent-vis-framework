# burr_kit

Reusable Burr architecture for building agentic subsystems inside agent-vis
workflows. Ported (cleaned up, generalised) from
`burr-combinatorial-testing/src/atf`. **No ATF workflows were copied** — only
the framework layers.

## Modules

| Module | Purpose |
|---|---|
| `app.burr_kit.presets` | File-backed `PresetConfig` (description, workflow scope, free-form `config` dict, free-form `overrides` list). Loader walks `<presets_root>/<name>/preset.yaml` and `<agent>.md` prompts. |
| `app.burr_kit.prompt_loader` | `PromptLoader(workflow_dir, preset_dir)`: resolves prompts as preset → workflow → default. |
| `app.burr_kit.agent_runner` | `AgentRunner(provider, prompt_loader, model)` runs a named agent against any `ModelProvider` and optionally validates the response against a pydantic schema (with 1 retry on JSON failure). |
| `app.burr_kit.subprocess_runner` | `SubprocessRunner` with timeout, env allowlist, dry-run, and optional `coverage` wrapping. |
| `app.burr_kit.parameter_space` | Pydantic models for combinatorial parameter spaces. Example schema; nothing in `burr_kit` imports it. |
| `app.burr_kit.testforge` | Example pluggable client interface (`TestForgeClient` protocol + `FakeTestForgeClient` + `TestForgeHTTPBridgeClient`). Reference only. |

## Factory contract

`BurrSubsystemNode` inspects the factory signature and only injects the
kwargs it sees. Declaring any of these makes them automatic:

```python
def build_my_app(
    *,
    agent_runner: AgentRunner | None = None,
    prompt_loader: PromptLoader | None = None,
    preset: PresetConfig | None = None,
    model_provider: ModelProvider | None = None,
    # plus any factory inputs you map from workflow state via input_map
) -> ApplicationBuilder: ...
```

The node also continues to inject `ollama_model` / `ollama_base_url` for
Ollama-backed factories to preserve the existing contract.

## Workflow YAML knobs

```yaml
config:
  app_module: app.subsystems.examples.two_step_agent
  app_factory: build_two_step_app
  preset: example_strict                       # name under presets_root
  presets_root: presets                        # default: configs/presets
  prompt_dir: prompts/workflows/burr_kit_demo  # workflow-level overrides
  halt_after: [act]
```

Relative `preset` and `prompt_dir` paths are resolved under
`${WORKFLOW_CONFIG_DIR}` (default `configs/`).

## See also

- `configs/workflows/burr_kit_demo.yaml` — full working example.
- `configs/presets/example_strict/` — preset folder layout.
- `app/subsystems/examples/two_step_agent.py` — factory that declares all
  injection points.
