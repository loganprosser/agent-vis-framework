"""Example Strands ``Agent`` factory for ``StrandsAgentNode``.

The factory takes the prompt input via workflow ``input_map`` (we accept
``topic`` here but don't otherwise use it — the node hands the agent the
resolved prompt directly). It accepts an optional ``model_provider`` so
``StrandsAgentNode`` can hand it the workflow-configured provider; if that
provider is not OpenAI-compatible, the agent falls back to Strands'
``BedrockModel`` default behaviour.

This file is illustrative only — installing ``strands-agents`` is
required to actually run it (``pip install -e ".[strands]"``).
"""

from __future__ import annotations

from typing import Any


def build_research_agent(
    *,
    topic: str | None = None,
    model_provider: Any = None,
    tools: dict[str, Any] | None = None,
) -> Any:
    """Return a configured ``strands.Agent`` instance."""
    from strands import Agent  # type: ignore[import-not-found]

    system_prompt = (
        "You are a research assistant. Answer the user concisely. If you do "
        "not know something, say so plainly. Cite sources when you can."
    )

    # When a LiteLLM-compatible provider was wired in, derive a Strands
    # ``LiteLLMModel`` from its base_url + api key env. Otherwise fall back
    # to the Strands default (Bedrock).
    model_arg: Any | None = None
    if model_provider is not None and hasattr(model_provider, "config"):
        try:
            from strands.models.litellm import LiteLLMModel  # type: ignore[import-not-found]

            model_arg = LiteLLMModel(
                model_id=model_provider.default_model,
                client_args={
                    "api_base": model_provider.config.get("base_url"),
                },
            )
        except Exception:
            model_arg = None

    return Agent(model=model_arg, system_prompt=system_prompt)
