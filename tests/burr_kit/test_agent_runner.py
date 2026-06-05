from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from app.burr_kit.agent_runner import AgentRunner, _extract_json
from app.burr_kit.prompt_loader import PromptLoader
from app.models.base import ModelProvider, ModelRequest, ModelResponse


class StubProvider(ModelProvider):
    def __init__(self, responses: list[str]) -> None:
        super().__init__("stub", "stub-model", {})
        self.responses = list(responses)
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        text = self.responses.pop(0) if self.responses else ""
        return ModelResponse(text=text, raw={"stub": True})


class Person(BaseModel):
    name: str
    age: int


@pytest.mark.asyncio
async def test_run_returns_plain_text_when_no_schema() -> None:
    provider = StubProvider(["hello"])
    runner = AgentRunner(provider)
    result = await runner.run(
        "writer", default_prompt="be brief", user_message="say hi"
    )
    assert result.text == "hello"
    assert result.parsed is None
    assert provider.calls[0].system_prompt == "be brief"


@pytest.mark.asyncio
async def test_run_parses_fenced_json_against_schema() -> None:
    provider = StubProvider(['```json\n{"name": "Ada", "age": 30}\n```'])
    runner = AgentRunner(provider)
    result = await runner.run(
        "extractor",
        default_prompt="emit JSON",
        user_message="ada is 30",
        schema=Person,
    )
    assert isinstance(result.parsed, Person)
    assert result.parsed.name == "Ada"


@pytest.mark.asyncio
async def test_run_retries_once_on_parse_failure() -> None:
    provider = StubProvider(["not json at all", '{"name":"Ada","age":30}'])
    runner = AgentRunner(provider)
    result = await runner.run(
        "extractor",
        default_prompt="emit JSON",
        user_message="ada is 30",
        schema=Person,
    )
    assert isinstance(result.parsed, Person)
    assert len(provider.calls) == 2
    # Second call's user message must carry the retry hint.
    assert "previous response" in provider.calls[1].messages[0]["content"]


@pytest.mark.asyncio
async def test_run_reports_parse_error_after_two_failures() -> None:
    provider = StubProvider(["nope", "still nope"])
    runner = AgentRunner(provider)
    result = await runner.run(
        "extractor", default_prompt="emit JSON", user_message="x", schema=Person
    )
    assert result.parsed is None
    assert result.parse_error is not None
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_prompt_loader_overrides_default_prompt(tmp_path: Path) -> None:
    workflow = tmp_path / "wf"
    workflow.mkdir()
    (workflow / "writer.md").write_text("override prompt")

    provider = StubProvider(["ok"])
    runner = AgentRunner(provider, prompt_loader=PromptLoader(workflow_dir=workflow))
    await runner.run("writer", default_prompt="default", user_message="hi")
    assert provider.calls[0].system_prompt == "override prompt"


def test_extract_json_accepts_bare_and_fenced_forms() -> None:
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n[1,2]\n```') == [1, 2]
    assert _extract_json("not json") is None
