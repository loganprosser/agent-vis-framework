# Demos

Four runnable demos that exercise every milestone landed in this branch
end-to-end. All four are covered by tests in `tests/demos/` against a
deterministic scripted provider, and all four are runnable against
**mock**, **local Ollama**, or **any LiteLLM/RITS endpoint** registered
via `./configure-model.sh`.

## Quick reference

| Demo | Shows off | LLM required? | Workflow |
|------|-----------|---------------|----------|
| [combinatorial_calc](combinatorial_calc/README.md) | M2 `burr_kit.testforge` + `SubprocessRunner` | no | `demo_combinatorial_calc` |
| [research_assistant](research_assistant/README.md) | M4 ReAct orchestrator (tools + subagents + MCP discovery) | yes | `demo_react_research_assistant` |
| [burr_code_review](burr_code_review/README.md) | M2 `burr_kit` injection + M3 Mermaid runtime viz, with two presets | yes | `demo_burr_code_review` |
| [hybrid_pipeline](hybrid_pipeline/README.md) | M2 + M4 composition (ReAct feeding a Burr subsystem) | yes | `demo_hybrid_pipeline` |

## Run any demo

### 1. Quickest: pure Python, no model

```bash
python -m examples.run combinatorial_calc
```

That demo never talks to a model. Use it as your first sanity check after
a clean clone — if it returns a 10/10 pass report, the framework is wired
correctly.

### 2. Interactive picker (fzf)

```bash
./examples/run_demo.sh
# pick demo → pick provider → run
```

The picker reads provider ids straight out of `configs/models.yaml`, so
once you've run `./configure-model.sh` (M1) the right options appear.

### 3. Direct invocation

```bash
python -m examples.run <demo> --provider <id> --inputs '<json>'
```

Supported `--provider` ids come from `configs/models.yaml`. Pass
`--inputs` to override the demo's defaults (the JSON is merged on top of
them). `--preset <name>` works on demos that honour a preset (currently
`burr_code_review`).

## End-to-end with a real model

### Local Ollama

```bash
# One-time: register an Ollama provider with fzf.
./configure-model.sh --provider ollama
# Now any demo can target it.
python -m examples.run research_assistant --provider ollama_local
```

### LiteLLM proxy

```bash
# Bring up any OpenAI-compatible LiteLLM proxy first (IBM-AI-Setup makes
# this easy if you have a RITS key handy).
./configure-model.sh --provider litellm \
  --model gpt-4o-mini --base-url http://127.0.0.1:4000/v1
python -m examples.run burr_code_review --provider litellm_proxy
```

### IBM RITS

```bash
# Populate the RITS catalog (Playwright; one-time):
python scripts/providers/rits/scrape_rits_models.py
./configure-model.sh --provider rits  # picks from the scraped catalog
python -m examples.run hybrid_pipeline --provider rits_default
```

## What the UI does while a demo runs

Start the React control plane (`./start.sh`) before running a demo if you
want to watch:

- **Research assistant** — the runtime event timeline shows
  `react_thought → react_action → react_observation` triplets per
  iteration, ending in `react_final`.
- **Burr code review** — open the `review_subsystem` node; the Mermaid
  panel (M3) highlights `read_target → run_lint → write_review →
  summarize` live as the Burr application advances.
- **Hybrid pipeline** — combines the two: ReAct timeline on the left,
  plan→act Burr graph on the right.

## Tests

All four demos are exercised by `tests/demos/`:

```bash
pytest tests/demos -v
```

Each test reuses a `ScriptedProvider` fixture from `tests/demos/conftest.py`
that swaps every provider id in the workflow for a deterministic stub. If
the wiring breaks, the tests fail before you spend an LLM token.
