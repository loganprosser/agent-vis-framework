"""Reusable Burr architecture, ported from burr-combinatorial-testing/atf.

This package is intentionally framework-only: nothing here defines a workflow
or an LLM agent specific to test-generation. Build your own Burr Applications
on top of these primitives:

- ``presets``: file-backed tuning bundles applied to a Burr factory call.
- ``prompt_loader``: preset → workflow → default prompt resolution chain.
- ``agent_runner``: minimal LLM agent dispatcher with structured-response
  parsing and 1-retry on JSON failure.
- ``subprocess_runner``: safe command execution with timeout, env allowlist,
  dry-run, and optional code-coverage wrapping.
- ``testforge``: example pluggable client (Fake / HTTP) showing the protocol
  shape; not required by the rest of the kit.
"""

from app.burr_kit.agent_runner import AgentResult, AgentRunner
from app.burr_kit.presets import PresetConfig, list_presets, load_preset, load_preset_prompts
from app.burr_kit.prompt_loader import PromptLoader
from app.burr_kit.subprocess_runner import CoverageConfig, RunnerConfig, RunResult, SubprocessRunner

__all__ = [
    "AgentResult",
    "AgentRunner",
    "CoverageConfig",
    "PresetConfig",
    "PromptLoader",
    "RunResult",
    "RunnerConfig",
    "SubprocessRunner",
    "list_presets",
    "load_preset",
    "load_preset_prompts",
]
