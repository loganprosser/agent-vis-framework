# Demo 4 — Hybrid pipeline (composition showcase)

Confirms that the new node types compose: a `react_orchestrator` feeding
its `answer` into a `burr_subsystem` that runs the `burr_kit` two-step
agent factory.

```text
research (react_orchestrator) ──► refine (burr_subsystem, two_step_agent)
       inputs.topic                 task = research.answer
       outputs.answer                outputs.plan, outputs.answer
```

This is the demo to run when you want to see all the moving parts on one
screen: the ReAct timeline on the left, the Mermaid live-highlighted
plan→act graph on the right.

## Files

- `configs/workflows/demo_hybrid_pipeline.yaml` — workflow.
- Reuses `app/subsystems/examples/two_step_agent.py` from M2.

## Run it

```bash
python -m examples.run hybrid_pipeline --provider mock
python -m examples.run hybrid_pipeline --provider ollama_local \
  --inputs '{"topic": "Apache Burr"}'
python -m examples.run hybrid_pipeline --provider litellm_proxy \
  --inputs '{"topic": "combinatorial test reduction"}'
```
