from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from app.schemas.workflow import McpServerConfig


class StdioMcpClient:
    """Minimal MCP stdio client for initialize, tools/list, and tools/call.

    Supports both Content-Length framed and newline-delimited JSON (NDJSON)
    transports. Sends in NDJSON format (compatible with the official TypeScript
    MCP SDK) and auto-detects the server's response format on first read.
    """

    def __init__(self, server: McpServerConfig, project_root: Path | str = ".") -> None:
        self.server = server
        self.project_root = Path(project_root).resolve()
        self._request_id = 0
        self._server_uses_content_length: bool | None = None

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
        empty_parts = [(i, part) for i, (orig, part) in enumerate(zip(self.server.command, command)) if not part and orig]
        if empty_parts:
            indices = ", ".join(f"arg[{i}] (from {orig!r})" for i, orig in empty_parts)
            raise RuntimeError(
                f"MCP server {self.server.id}: env var expansion produced empty string for {indices}. "
                f"Set the required environment variables before running this workflow."
            )

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
        self._server_uses_content_length = None
        try:
            await self._initialize()
            return await asyncio.wait_for(operation(), timeout=self.server.timeout_seconds)
        except TimeoutError:
            stderr = await self._read_stderr()
            raise RuntimeError(
                f"MCP server {self.server.id}: operation timed out after {self.server.timeout_seconds}s. "
                f"Stderr: {stderr or '(empty)'}"
            )
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
                error = message["error"]
                error_msg = error if isinstance(error, str) else error.get("message", str(error))
                raise RuntimeError(f"MCP server {self.server.id}: {error_msg}")
            return message.get("result", {})

    async def _send(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message) + "\n"
        assert self._process.stdin is not None
        self._process.stdin.write(payload.encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if self._server_uses_content_length is None:
            return await self._read_message_auto_detect()
        if self._server_uses_content_length:
            return await self._read_message_content_length()
        return await self._read_message_ndjson()

    async def _read_message_auto_detect(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        line = await self._process.stdout.readline()
        if not line:
            stderr = await self._read_stderr()
            raise RuntimeError(f"MCP server {self.server.id} closed stdout. Stderr: {stderr or '(empty)'}")

        decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if decoded.startswith("Content-Length:"):
            self._server_uses_content_length = True
            headers: dict[str, str] = {}
            key, _, value = decoded.partition(":")
            headers[key.lower().strip()] = value.strip()
            while True:
                next_line = await self._process.stdout.readline()
                if not next_line:
                    stderr = await self._read_stderr()
                    raise RuntimeError(f"MCP server {self.server.id} closed stdout. Stderr: {stderr or '(empty)'}")
                next_decoded = next_line.decode("ascii").strip()
                if not next_decoded:
                    break
                nk, _, nv = next_decoded.partition(":")
                headers[nk.lower().strip()] = nv.strip()
            content_length = int(headers.get("content-length", "0"))
            if content_length <= 0:
                raise RuntimeError(f"MCP server {self.server.id}: message missing Content-Length.")
            payload = await self._process.stdout.readexactly(content_length)
            return json.loads(payload.decode("utf-8"))
        else:
            self._server_uses_content_length = False
            return json.loads(decoded)

    async def _read_message_content_length(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        headers: dict[str, str] = {}
        while True:
            line = await self._process.stdout.readline()
            if not line:
                stderr = await self._read_stderr()
                raise RuntimeError(f"MCP server {self.server.id} closed stdout. Stderr: {stderr or '(empty)'}")
            decoded = line.decode("ascii").strip()
            if not decoded:
                break
            key, _, value = decoded.partition(":")
            headers[key.lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise RuntimeError(f"MCP server {self.server.id}: message missing Content-Length.")
        payload = await self._process.stdout.readexactly(content_length)
        return json.loads(payload.decode("utf-8"))

    async def _read_message_ndjson(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        while True:
            line = await self._process.stdout.readline()
            if not line:
                stderr = await self._read_stderr()
                raise RuntimeError(f"MCP server {self.server.id} closed stdout. Stderr: {stderr or '(empty)'}")
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                continue
            return json.loads(decoded)

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
        result = (
            value.replace("{python}", sys.executable)
            .replace("{project_root}", str(self.project_root))
            .replace("{cwd}", str(self.project_root))
        )

        def _env_replace(match: re.Match[str]) -> str:
            return os.environ.get(match.group(1), "")

        result = re.sub(r"\{env:([^}]+)\}", _env_replace, result)
        return result
