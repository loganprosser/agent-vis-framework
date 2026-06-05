"""Minimal LLM agent dispatcher with structured-response parsing.

This is a generalised port of ``atf.llm.agents.AgentRunner``. The original
hard-coded ATF-specific agent names; here the runner is name-agnostic — pass
any ``agent_name`` and a default system prompt, and it resolves the active
prompt via :class:`PromptLoader`, dispatches to a :class:`ModelProvider`, and
optionally validates the response against a pydantic schema (with one retry
on JSON failure).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.burr_kit.prompt_loader import PromptLoader
from app.models.base import ModelProvider, ModelRequest


@dataclass
class AgentResult:
    text: str
    parsed: Any | None = None
    parse_error: str | None = None
    raw: dict[str, Any] | None = None


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str) -> Any | None:
    """Pull a JSON value out of an LLM response, accepting fenced or bare forms."""
    if not text:
        return None
    match = _JSON_FENCE_RE.search(text)
    if match:
        candidate = match.group(1)
    else:
        candidate = text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


class AgentRunner:
    """Run named agents against a single ``ModelProvider``.

    Parameters:
        provider: any registered ``ModelProvider`` (mock, openai, rits, ...).
        prompt_loader: optional ``PromptLoader``; if absent, default prompts
                       are used verbatim with no file resolution.
        model: optional model name override. Defaults to ``provider.default_model``.
    """

    def __init__(
        self,
        provider: ModelProvider,
        prompt_loader: PromptLoader | None = None,
        model: str | None = None,
    ) -> None:
        self.provider = provider
        self.prompt_loader = prompt_loader
        self.model = model or provider.default_model

    def resolve_prompt(self, agent_name: str, default_prompt: str) -> str:
        if self.prompt_loader is None:
            return default_prompt
        return self.prompt_loader.load_prompt(agent_name, default_prompt)

    async def run(
        self,
        agent_name: str,
        *,
        default_prompt: str,
        user_message: str,
        schema: type[BaseModel] | None = None,
        retry_on_parse_failure: bool = True,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        system = self.resolve_prompt(agent_name, default_prompt)
        attempt_user = user_message
        last_response = None
        last_error: str | None = None

        for attempt in range(2 if retry_on_parse_failure else 1):
            request = ModelRequest(
                model=self.model,
                system_prompt=system,
                messages=[{"role": "user", "content": attempt_user}],
                context=context or {},
            )
            response = await self.provider.generate(request)
            last_response = response

            if schema is None:
                return AgentResult(text=response.text, raw=response.raw)

            parsed_json = _extract_json(response.text)
            if parsed_json is None:
                last_error = "Response did not contain parseable JSON."
            else:
                try:
                    parsed = schema.model_validate(parsed_json)
                    return AgentResult(text=response.text, parsed=parsed, raw=response.raw)
                except ValidationError as exc:
                    last_error = f"Schema validation failed: {exc.errors()[:3]}"

            if attempt == 0 and retry_on_parse_failure:
                attempt_user = (
                    f"{user_message}\n\nYour previous response could not be parsed. "
                    f"Error: {last_error}\nReply with valid JSON only — no prose, no code fences."
                )

        return AgentResult(
            text=last_response.text if last_response else "",
            parsed=None,
            parse_error=last_error,
            raw=last_response.raw if last_response else None,
        )
