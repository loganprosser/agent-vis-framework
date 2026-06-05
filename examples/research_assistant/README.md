# Demo 1 — ReAct research assistant

Showcases **M4** (`react_orchestrator` node). A single node drives a strict
Thought/Action/Action Input loop that picks each turn between:

| Catalog source       | Example actions                              |
|----------------------|----------------------------------------------|
| Declared tool        | `builtin_demo_mcp`                           |
| Inline subagent      | `outliner`, `summarizer`                     |
| MCP-discovered tool  | `builtin_demo_mcp.echo`, `builtin_demo_mcp.workflow_hint` |

The loop terminates when the model emits `Action: final_answer`.

## Files

- `configs/workflows/demo_react_research_assistant.yaml` — workflow.
- `tests/demos/test_demo_react_research_assistant.py` — scripted ReAct trace
  asserting catalog assembly + termination paths.

## Run it

```bash
# Pure-mock (no LLM, deterministic — terminates at max_iterations).
python -m examples.run research_assistant --provider mock

# Local Ollama.
./configure-model.sh --provider ollama --provider-id ollama_local \
  --model llama3.1:8b --context-length 8192
python -m examples.run research_assistant --provider ollama_local \
  --inputs '{"objective": "Explain combinatorial testing in two sentences"}'

# LiteLLM-compatible endpoint (e.g. RITS via IBM-AI-Setup).
./configure-model.sh --provider litellm --provider-id litellm_proxy \
  --model GLM-5.1-FP8 --base-url http://127.0.0.1:4000/v1
python -m examples.run research_assistant --provider litellm_proxy \
  --inputs '{"objective": "Explain Burr state machines"}'
```

Open the React control plane at `http://127.0.0.1:5173/`, pick the demo, and
the runtime event timeline will show alternating `react_thought` →
`react_action` → `react_observation` events as the loop progresses.
