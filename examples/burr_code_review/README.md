# Demo 2 — Burr code review subsystem

Showcases **M2** (`burr_kit` injection: `AgentRunner`, `PromptLoader`,
`SubprocessRunner`, `PresetConfig`) and **M3** (live Mermaid runtime
visualizer). One `burr_subsystem` node, four Burr actions:

```text
read_target → run_lint → write_review → summarize
```

- `read_target` reads the target file (or accepts inline `file_content` from
  workflow inputs — convenient for tests).
- `run_lint` shells out via `SubprocessRunner`. The command template comes
  from the active preset.
- `write_review` and `summarize` call agents through `AgentRunner` whose
  prompts are resolved by `PromptLoader` (preset → workflow → default).

## Presets

| Preset             | Lint command                                | Prompt tweaks |
|--------------------|---------------------------------------------|---------------|
| `strict_review`    | `ruff check --quiet {target_path}`          | line-numbered bullets, severity-first summary |
| `friendly_review`  | dry-run echo, no real lint                  | leads with one strength, then suggestions |

Switch by editing the `preset:` field on the burr_subsystem node in
`configs/workflows/demo_burr_code_review.yaml`, or pass
`--preset friendly_review` to `examples/run.py`.

## Files

- `app/subsystems/examples/code_review_burr.py` — factory.
- `configs/workflows/demo_burr_code_review.yaml` — workflow.
- `configs/presets/strict_review/` and `configs/presets/friendly_review/`.
- `configs/prompts/workflows/demo_burr_code_review/review.md` — workflow-level
  prompt that fills in if no preset overrides it.
- `examples/burr_code_review/sample_calc.py` — default review target.

## Run it

```bash
# Mock provider — short-circuits the LLM actions; still exercises the
# subprocess runner.
python -m examples.run burr_code_review --provider mock

# Ollama.
python -m examples.run burr_code_review --provider ollama_local \
  --inputs '{"target_path": "examples/burr_code_review/sample_calc.py"}'

# Friendly preset against LiteLLM.
python -m examples.run burr_code_review --provider litellm_proxy \
  --preset friendly_review
```

While the workflow is running, open
`http://127.0.0.1:5173/`, select `review_subsystem`, and watch the
runtime graph highlight `read_target → run_lint → write_review → summarize`
in turn.
