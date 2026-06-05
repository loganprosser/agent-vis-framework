"""Combinatorial calculator demo — pure-Python, no LLM required.

Uses :class:`FakeTestForgeClient` to greedily reduce a (op, a, b)
parameter space to a pairwise-covering test suite, then executes each
row with :class:`SubprocessRunner` against a small Python calculator
inline. Writes a simple Markdown-ish report.

State machine:

    build_model → reduce → execute → report

The factory exposes both the parameter space and the command template
so callers can override either from the workflow YAML's ``input_map`` or
a preset.
"""

from __future__ import annotations

from typing import Any

from burr.core import ApplicationBuilder, State, action

from app.burr_kit.parameter_space import ParameterModel, TestConstraint, TestParameter
from app.burr_kit.presets import PresetConfig
from app.burr_kit.subprocess_runner import RunnerConfig, SubprocessRunner, render_command
from app.burr_kit.testforge.fake import FakeTestForgeClient

DEFAULT_PARAMETERS: list[TestParameter] = [
    TestParameter(name="op", values=["add", "sub", "mul", "div"]),
    TestParameter(name="a", values=["0", "1", "-5", "100"]),
    TestParameter(name="b", values=["0", "1", "7"]),
]
DEFAULT_CONSTRAINTS: list[TestConstraint] = [
    TestConstraint(
        rule='IF op = "div" THEN b != "0"',
        description="prevent division by zero in the generated suite",
    ),
]

DEFAULT_COMMAND_TEMPLATE = (
    "python -c \"import sys; op, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]); "
    "r = (a+b) if op=='add' else (a-b) if op=='sub' else (a*b) if op=='mul' else (a//b); "
    "print(r)\" {op} {a} {b}"
)


def build_combinatorial_calc_app(
    command_template: str | None = None,
    coverage_level: int = 2,
    *,
    preset: PresetConfig | None = None,
) -> ApplicationBuilder:
    """Build the combinatorial-calc Burr application."""

    command_template = command_template or DEFAULT_COMMAND_TEMPLATE
    preset_config = (preset.config if preset else {}) or {}
    runner = SubprocessRunner(
        RunnerConfig(
            timeout=float(preset_config.get("timeout", 5.0)),
            dry_run=bool(preset_config.get("dry_run", False)),
        )
    )
    max_executions = int(preset_config.get("max_executions", 10))

    @action(reads=[], writes=["param_model", "status"])
    def build_model(state: State) -> tuple[dict, State]:
        model = ParameterModel(
            parameters=DEFAULT_PARAMETERS,
            constraints=DEFAULT_CONSTRAINTS,
            coverage_level=coverage_level,
        )
        dumped = model.model_dump()
        return {"param_model": dumped}, state.update(param_model=dumped, status="modeled")

    @action(reads=["param_model"], writes=["reduction", "status"])
    def reduce(state: State) -> tuple[dict, State]:
        model = ParameterModel.model_validate(state["param_model"])
        client = FakeTestForgeClient()
        result = client.generate_test_suite(model)
        dumped = result.model_dump()
        return {"reduction": dumped}, state.update(reduction=dumped, status="reduced")

    @action(
        reads=["reduction", "command_template"],
        writes=["executions", "passed", "failed", "status"],
    )
    def execute(state: State) -> tuple[dict, State]:
        template = state.get("command_template") or command_template
        cases = (state["reduction"] or {}).get("test_cases") or []
        executions: list[dict[str, Any]] = []
        passed = 0
        failed = 0
        for case in cases[:max_executions]:
            values = case.get("values", {})
            try:
                cmd = render_command(template, values)
            except KeyError as exc:
                executions.append(
                    {
                        "values": values,
                        "command": template,
                        "stdout": "",
                        "stderr": f"missing key in template: {exc}",
                        "exit_code": -2,
                    }
                )
                failed += 1
                continue
            result = runner.run(cmd)
            executions.append(
                {
                    "values": values,
                    "command": result.command,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "exit_code": result.exit_code,
                }
            )
            if result.exit_code == 0:
                passed += 1
            else:
                failed += 1
        return (
            {"executions": executions, "passed": passed, "failed": failed},
            state.update(executions=executions, passed=passed, failed=failed, status="executed"),
        )

    @action(reads=["executions", "passed", "failed"], writes=["report", "status"])
    def report(state: State) -> tuple[dict, State]:
        lines = [
            f"# Combinatorial calc report",
            f"- passed: {state.get('passed', 0)}",
            f"- failed: {state.get('failed', 0)}",
            "",
            "| op | a | b | exit | stdout |",
            "|----|---|---|------|--------|",
        ]
        for record in state.get("executions") or []:
            v = record.get("values", {})
            lines.append(
                f"| {v.get('op','')} | {v.get('a','')} | {v.get('b','')} | "
                f"{record.get('exit_code')} | {record.get('stdout','')} |"
            )
        text = "\n".join(lines)
        return {"report": text}, state.update(report=text, status="complete")

    return (
        ApplicationBuilder()
        .with_actions(
            build_model=build_model,
            reduce=reduce,
            execute=execute,
            report=report,
        )
        .with_transitions(
            ("build_model", "reduce"),
            ("reduce", "execute"),
            ("execute", "report"),
        )
        .with_entrypoint("build_model")
        .with_state(
            command_template=command_template,
            status="initialized",
        )
    )
