# Demo 3 — Combinatorial calculator

Pure-Python combinatorial testing showcase. **No LLM required** — this is
the demo to run if you just want to confirm the new framework primitives
(`burr_kit.testforge`, `burr_kit.subprocess_runner`) are wired correctly.

State machine:

```text
build_model → reduce → execute → report
```

- `build_model` declares a 3-parameter space `(op, a, b)` with a div-by-zero
  constraint, via `app.burr_kit.parameter_space`.
- `reduce` calls `FakeTestForgeClient.generate_test_suite()` to greedily
  reduce to a pairwise covering set.
- `execute` renders each row through `SubprocessRunner` against an inline
  Python calculator, recording stdout, stderr, exit_code, duration.
- `report` writes a Markdown summary.

## Files

- `app/subsystems/examples/combinatorial_calc.py` — factory.
- `configs/workflows/demo_combinatorial_calc.yaml` — workflow.

## Run it

```bash
# No provider needed — the subsystem never talks to a model.
python -m examples.run combinatorial_calc

# Override the command template (still no LLM):
python -m examples.run combinatorial_calc \
  --inputs '{"command_template": "echo {op} {a} {b}"}'
```

Use this demo as your first end-to-end sanity check after a fresh clone.
