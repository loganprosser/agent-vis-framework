"""Minimal Burr subsystem demonstrating ``burr_kit`` injection.

The factory signature declares ``agent_runner``, ``prompt_loader``, ``preset``,
and ``model_provider`` parameters. ``BurrSubsystemNode`` inspects the
signature and only injects the kwargs it sees, so the same factory works
from a Python script (no kwargs) or from an agent-vis workflow YAML (all
kwargs auto-wired).
"""

from __future__ import annotations

import asyncio
from typing import Any

from burr.core import ApplicationBuilder, State, action

from app.burr_kit.agent_runner import AgentRunner
from app.burr_kit.presets import PresetConfig
from app.burr_kit.prompt_loader import PromptLoader

PLAN_DEFAULT_PROMPT = (
    "You are a planner. Given the user's task, produce a one-line outline of "
    "the steps you would take. Keep it concrete and under 25 words."
)
ACT_DEFAULT_PROMPT = (
    "You are an executor. Given the plan, produce the final answer in one short "
    "paragraph. No preamble; just the answer."
)


def _run_agent_sync(agent: AgentRunner, name: str, default: str, user: str) -> str:
    return asyncio.run(
        agent.run(name, default_prompt=default, user_message=user)
    ).text.strip()


def build_two_step_app(
    task: str,
    *,
    agent_runner: AgentRunner | None = None,
    prompt_loader: PromptLoader | None = None,
    preset: PresetConfig | None = None,
    model_provider: Any = None,
) -> ApplicationBuilder:
    """Build a tiny plan→act Burr application.

    When ``agent_runner`` is missing, the actions short-circuit to a canned
    response so the example still runs offline.
    """

    use_mock = agent_runner is None
    style_hint = ""
    if preset and preset.config.get("style"):
        style_hint = f"\nStyle hint from preset: {preset.config['style']}"

    @action(reads=["task"], writes=["plan", "status"])
    def plan(state: State) -> tuple[dict, State]:
        if use_mock:
            text = f"[mock plan] {state['task']}"
        else:
            text = _run_agent_sync(
                agent_runner, "plan", PLAN_DEFAULT_PROMPT + style_hint, state["task"]
            )
        return {"plan": text}, state.update(plan=text, status="planned")

    @action(reads=["task", "plan"], writes=["answer", "status"])
    def act(state: State) -> tuple[dict, State]:
        if use_mock:
            text = f"[mock answer] {state['plan']}"
        else:
            text = _run_agent_sync(
                agent_runner,
                "act",
                ACT_DEFAULT_PROMPT + style_hint,
                f"Task: {state['task']}\nPlan: {state['plan']}",
            )
        return {"answer": text}, state.update(answer=text, status="complete")

    return (
        ApplicationBuilder()
        .with_actions(plan=plan, act=act)
        .with_transitions(("plan", "act"))
        .with_entrypoint("plan")
        .with_state(task=task, status="initialized")
    )
