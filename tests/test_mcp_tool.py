import pytest

from app.core.config_loader import ConfigLoader
from app.core.registry import ToolRegistry


@pytest.mark.asyncio
async def test_builtin_demo_mcp_lists_and_calls_tools() -> None:
    loader = ConfigLoader()
    registry = ToolRegistry({server.id: server for server in loader.load_mcps().servers})
    for tool_config in loader.load_tools().tools:
        registry.register_tool_config(tool_config)

    listed = await registry.get("builtin_demo_mcp").run(action="list_tools")
    called = await registry.get("builtin_demo_mcp").run(
        action="call_tool",
        name="echo",
        arguments={"message": "hello"},
    )

    assert listed.ok
    assert [tool["name"] for tool in listed.data["tools"]] == ["echo", "workflow_hint"]
    assert called.ok
    assert called.data["content"][0]["text"] == "hello"
