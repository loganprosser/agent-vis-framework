from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.schemas.workflow import McpServerConfig


class StdioMcpClient:
    """Minimal MCP stdio client for initialize, tools/list, and tools/call.

    This intentionally implements the small JSON-RPC surface this starter needs.
    It can be swapped later for the official MCP SDK without changing node code.
    """

    def __init__(self, server: McpServerConfig, project_root: Path | str = ".") -> None:
        self.server = server
        self.project_root = Path(project_root).resolve()
        self._request_id = 0

    async def list_tools(self) -> dict[str, Any]:
        return await self._with_session(lambda: self._request("tools/list", {}))

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._with_session(lambda: self._request("tools/call", {"name": name, "arguments": arguments or {}}))

    async def _with_session(self, operation):
        if not self.server.enabled:
            raise RuntimeError(f"MCP server is disabled: {self.server.id}")
        if self.server.transport != "stdio":
            raise RuntimeError(f"Unsupported MCP transport: {self.server.transport}")
        if not self.server.command:
            raise RuntimeError(f"MCP server has no command configured: {self.server.id}")

        command = [self._expand_token(part) for part in self.server.command]
        cwd = self._expand_token(self.server.cwd) if self.server.cwd else str(self.project_root)
        env = {**os.environ, **{key: self._expand_token(value) for key, value in self.server.env.items()}}

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = process
        try:
            await self._initialize()
            return await asyncio.wait_for(operation(), timeout=self.server.timeout_seconds)
        finally:
            await self._shutdown()

    async def _initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agentic-workflow-framework", "version": "0.1.0"},
            },
        )
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = await asyncio.wait_for(self._read_message(), timeout=self.server.timeout_seconds)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})

    async def _send(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        assert self._process.stdin is not None
        self._process.stdin.write(header + payload)
        await self._process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        headers: dict[str, str] = {}
        while True:
            line = await self._process.stdout.readline()
            if not line:
                stderr = await self._read_stderr()
                raise RuntimeError(f"MCP server closed stdout. {stderr}")
            decoded = line.decode("ascii").strip()
            if not decoded:
                break
            key, _, value = decoded.partition(":")
            headers[key.lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise RuntimeError("MCP message missing Content-Length.")
        payload = await self._process.stdout.readexactly(content_length)
        return json.loads(payload.decode("utf-8"))

    async def _shutdown(self) -> None:
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()

    async def _read_stderr(self) -> str:
        assert self._process.stderr is not None
        try:
            data = await asyncio.wait_for(self._process.stderr.read(), timeout=0.2)
        except TimeoutError:
            return ""
        return data.decode("utf-8", errors="replace").strip()

    def _expand_token(self, value: str | None) -> str:
        if value is None:
            return ""
        return (
            value.replace("{python}", sys.executable)
            .replace("{project_root}", str(self.project_root))
            .replace("{cwd}", str(self.project_root))
        )
