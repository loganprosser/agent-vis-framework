from __future__ import annotations

import json
import sys
from typing import Any


TOOLS = [
    {
        "name": "echo",
        "description": "Echo a message back from the built-in demo MCP server.",
        "inputSchema": {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
    },
    {
        "name": "workflow_hint",
        "description": "Return a short hint about configuring this workflow framework.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        decoded = line.decode("ascii").strip()
        if not decoded:
            break
        key, _, value = decoded.partition(":")
        headers[key.lower()] = value.strip()
    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    return json.loads(sys.stdin.buffer.read(content_length).decode("utf-8"))


def send(message: dict[str, Any]) -> None:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
    sys.stdout.buffer.flush()


def result(request_id: int | str, payload: dict[str, Any]) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "result": payload})


def error(request_id: int | str | None, message: str) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": message}})


def main() -> None:
    while True:
        message = read_message()
        if message is None:
            break
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "builtin-demo-mcp", "version": "0.1.0"},
                },
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            result(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            if tool_name == "echo":
                text = str(arguments.get("message", ""))
            elif tool_name == "workflow_hint":
                text = "Add MCP tools in configs/mcps.yaml, expose them in configs/tools.yaml, then attach the tool id to workflow nodes."
            else:
                error(request_id, f"Unknown tool: {tool_name}")
                continue
            result(request_id, {"content": [{"type": "text", "text": text}], "isError": False})
        else:
            error(request_id, f"Unsupported method: {method}")


if __name__ == "__main__":
    main()
