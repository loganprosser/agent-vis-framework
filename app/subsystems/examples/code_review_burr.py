"""Burr code-review subsystem using every ``burr_kit`` primitive.

State machine (Mermaid renders this live in the React inspector):

    read_target → run_lint → write_review → summarize

- ``read_target`` reads the target file (or accepts ``file_content``
  through the factory for tests).
- ``run_lint`` runs a shell command via :class:`SubprocessRunner`. The
  command template is preset-controlled (default: dry-run ``echo``).
- ``write_review`` calls the ``review`` agent through :class:`AgentRunner`
  with prompts resolved via :class:`PromptLoader`.
- ``summarize`` calls the ``summary`` agent.

Without an ``agent_runner`` (e.g. running this factory directly from a
script with no LLM wiring), the LLM actions short-circuit to canned
strings so the example still completes deterministically.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from burr.core import ApplicationBuilder, State, action

from app.burr_kit.agent_runner import AgentRunner
from app.burr_kit.presets import PresetConfig
from app.burr_kit.prompt_loader import PromptLoader
from app.burr_kit.subprocess_runner import RunnerConfig, SubprocessRunner

REVIEW_DEFAULT_PROMPT = (
    "You are a strict but constructive senior code reviewer. Read the file "
    "content and respond with at most 5 bullets identifying real issues "
    "(correctness, security, ergonomics). No filler, no praise."
)
SUMMARY_DEFAULT_PROMPT = (
    "Summarise the lint findings and code review into a single tight "
    "paragraph that a tech lead can act on. No bullet lists."
)


def _run_agent(agent: AgentRunner, name: str, default: str, user: str) -> str:
    return asyncio.run(
        agent.run(name, default_prompt=default, user_message=user)
    ).text.strip()


def build_code_review_app(
    target_path: str = "",
    *,
    file_content: str | None = None,
    agent_runner: AgentRunner | None = None,
    prompt_loader: PromptLoader | None = None,
    preset: PresetConfig | None = None,
    model_provider: Any = None,
) -> ApplicationBuilder:
    """Build the code-review Burr application.

    Preset config knobs honoured:
      - ``lint_command`` (default ``echo``-based stub)
      - ``subprocess.timeout`` (default 10s)
      - ``subprocess.dry_run`` (default True; off in CI-style strict preset)
    """

    preset_config = (preset.config if preset else {}) or {}
    lint_command_template = preset_config.get(
        "lint_command", "echo '[lint stub] no issues found in {target_path}'"
    )
    subprocess_cfg = preset_config.get("subprocess") or {}
    runner = SubprocessRunner(
        RunnerConfig(
            timeout=float(subprocess_cfg.get("timeout", 10.0)),
            dry_run=bool(subprocess_cfg.get("dry_run", True)),
        )
    )
    style_suffix = ""
    if preset_config.get("style"):
        style_suffix = f"\nStyle constraint from preset: {preset_config['style']}"

    use_mock = agent_runner is None
    seeded_content = file_content

    @action(reads=["target_path"], writes=["file_content", "status"])
    def read_target(state: State) -> tuple[dict, State]:
        path = state.get("target_path", "")
        if seeded_content is not None:
            content = seeded_content
        elif path and Path(path).exists():
            try:
                content = Path(path).read_text(encoding="utf-8")
            except OSError as exc:
                content = ""
                return (
                    {"file_content": content, "status": f"read_error:{exc}"},
                    state.update(file_content=content, status="read_error"),
                )
        else:
            content = ""
        clipped = content[:4000]
        return {"file_content": clipped}, state.update(file_content=clipped, status="read")

    @action(reads=["target_path"], writes=["lint_output", "status"])
    def run_lint(state: State) -> tuple[dict, State]:
        command = lint_command_template.format(target_path=state.get("target_path", ""))
        result = runner.run(command)
        return {
            "lint_output": result.stdout,
        }, state.update(lint_output=result.stdout, status="linted")

    @action(reads=["file_content"], writes=["review", "status"])
    def write_review(state: State) -> tuple[dict, State]:
        if use_mock:
            text = f"[mock review] {len(state.get('file_content') or '')} chars analysed"
        else:
            text = _run_agent(
                agent_runner,
                "review",
                REVIEW_DEFAULT_PROMPT + style_suffix,
                state.get("file_content") or "",
            )
        return {"review": text}, state.update(review=text, status="reviewed")

    @action(reads=["review", "lint_output"], writes=["summary", "status"])
    def summarize(state: State) -> tuple[dict, State]:
        combined = (
            f"Lint output:\n{state.get('lint_output') or ''}\n\n"
            f"Review:\n{state.get('review') or ''}"
        )
        if use_mock:
            text = f"[mock summary] {combined[:160]}"
        else:
            text = _run_agent(
                agent_runner,
                "summary",
                SUMMARY_DEFAULT_PROMPT + style_suffix,
                combined,
            )
        return {"summary": text}, state.update(summary=text, status="complete")

    return (
        ApplicationBuilder()
        .with_actions(
            read_target=read_target,
            run_lint=run_lint,
            write_review=write_review,
            summarize=summarize,
        )
        .with_transitions(
            ("read_target", "run_lint"),
            ("run_lint", "write_review"),
            ("write_review", "summarize"),
        )
        .with_entrypoint("read_target")
        .with_state(target_path=target_path, status="initialized")
    )
