from __future__ import annotations

import json
import os
import re
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from burr.core import ApplicationBuilder, State, action, default, when

# Accept a solution when the critic assigns this score or higher (0-10 scale).
ACCEPT_THRESHOLD = 7
DEFAULT_MAX_ITERATIONS = 3


def _call_ollama_sync(
    system_prompt: str,
    user_message: str,
    *,
    model: str,
    base_url: str,
    timeout: float = 120.0,
) -> str:
    """Synchronous Ollama /api/chat call. Returns the response text or an error string."""
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3},
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        return str(body.get("message", {}).get("content") or "")
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        return f"[ollama error] {exc}"


def _parse_quality_score(text: str) -> int:
    """Extract an integer 0-10 quality score from critic response text.

    Tries patterns like 'Quality score: 8/10', '8/10', 'Score: 8'.
    Returns 5 (neutral) when no match is found.
    """
    patterns = [
        r"quality\s+score[:\s]+(\d+)\s*/\s*10",
        r"score[:\s]+(\d+)\s*/\s*10",
        r"(\d+)\s*/\s*10",
        r"score[:\s]+(\d+)",
        r"quality[:\s]+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            score = int(match.group(1))
            if 0 <= score <= 10:
                return score
    return 5


def build_iterative_code_reviewer(
    problem_spec: str,
    *,
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    _override_call_model: Callable[[str, str], str] | None = None,
) -> ApplicationBuilder:
    """Build a Burr app that iteratively drafts and critiques code until quality threshold.

    Loop: draft_solution → critique_solution → evaluate_quality → (refining) back to draft
                                                                 → (done)     finalize_solution

    The loop exits when quality_score >= ACCEPT_THRESHOLD or iteration >= max_iterations.
    Use halt_after: [finalize_solution] in the parent workflow config.

    Args:
        problem_spec:          Clear problem statement passed from the parent workflow.
        ollama_model:          Model name override; falls back to OLLAMA_MODEL env var or 'llama3.2'.
        ollama_base_url:       Ollama server URL; falls back to OLLAMA_BASE_URL or localhost.
        max_iterations:        Hard cap on draft-critique cycles.
        _override_call_model:  Inject a callable (system_prompt, user_message) -> str for tests.
    """
    model = ollama_model or os.environ.get("OLLAMA_MODEL", "llama3.2")
    base_url = ollama_base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    def _call(system_prompt: str, user_message: str) -> str:
        if _override_call_model is not None:
            return _override_call_model(system_prompt, user_message)
        return _call_ollama_sync(system_prompt, user_message, model=model, base_url=base_url)

    @action(
        reads=["problem", "critique", "iteration", "max_iterations"],
        writes=["solution", "iteration", "status"],
    )
    def draft_solution(state: State) -> tuple[dict, State]:
        iteration = state["iteration"] + 1
        critique = state["critique"]

        if critique:
            user_msg = (
                f"Problem:\n{state['problem']}\n\n"
                f"Previous critique:\n{critique}\n\n"
                "Revise the solution to address the critique. Return only the improved code."
            )
        else:
            user_msg = (
                f"Problem:\n{state['problem']}\n\n"
                "Write a complete, correct solution. Return only the code."
            )

        system_prompt = (
            "You are an expert software engineer. Write clean, correct, well-structured code. "
            "Include only concise inline comments — no lengthy prose."
        )
        solution = _call(system_prompt, user_msg)
        return (
            {"iteration": iteration},
            state.update(solution=solution, iteration=iteration, status="critiquing"),
        )

    @action(
        reads=["problem", "solution"],
        writes=["critique", "quality_score", "status"],
    )
    def critique_solution(state: State) -> tuple[dict, State]:
        system_prompt = (
            "You are a senior code reviewer. Evaluate the solution for correctness, "
            "edge case handling, clarity, and adherence to best practices. "
            "End your review with exactly one line: 'Quality score: X/10' where X is 0-10."
        )
        user_msg = (
            f"Problem:\n{state['problem']}\n\n"
            f"Solution:\n{state['solution']}\n\n"
            "Provide a focused critique and conclude with 'Quality score: X/10'."
        )
        critique = _call(system_prompt, user_msg)
        score = _parse_quality_score(critique)
        return (
            {"critique": critique, "quality_score": score},
            state.update(critique=critique, quality_score=score, status="evaluating"),
        )

    @action(
        reads=["quality_score", "iteration", "max_iterations"],
        writes=["status"],
    )
    def evaluate_quality(state: State) -> tuple[dict, State]:
        """Route: continue refining or finalize based on score and iteration count."""
        accepted = state["quality_score"] >= ACCEPT_THRESHOLD
        exhausted = state["iteration"] >= state["max_iterations"]
        new_status = "done" if (accepted or exhausted) else "refining"
        return ({}, state.update(status=new_status))

    @action(
        reads=["solution", "critique", "quality_score", "iteration"],
        writes=["final_solution", "final_score", "iterations_used", "accepted"],
    )
    def finalize_solution(state: State) -> tuple[dict, State]:
        accepted = state["quality_score"] >= ACCEPT_THRESHOLD
        result = {
            "final_solution": state["solution"],
            "final_score": state["quality_score"],
            "iterations_used": state["iteration"],
            "accepted": accepted,
        }
        return (result, state.update(**result, status="complete"))

    return (
        ApplicationBuilder()
        .with_actions(
            draft_solution=draft_solution,
            critique_solution=critique_solution,
            evaluate_quality=evaluate_quality,
            finalize_solution=finalize_solution,
        )
        .with_transitions(
            ("draft_solution", "critique_solution", default),
            ("critique_solution", "evaluate_quality", default),
            ("evaluate_quality", "draft_solution", when(status="refining")),
            ("evaluate_quality", "finalize_solution", when(status="done")),
        )
        .with_entrypoint("draft_solution")
        .with_state(
            problem=problem_spec,
            solution="",
            critique="",
            quality_score=0,
            iteration=0,
            max_iterations=max_iterations,
            status="initialized",
        )
    )
