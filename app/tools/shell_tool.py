from __future__ import annotations

import asyncio
import shlex
from typing import Any

from app.tools.base import Tool, ToolResult


class ShellTool(Tool):
    """Restricted shell adapter.

    Disabled by default in configs. When enabled, only commands whose first token
    appears in allowed_commands will run.
    """

    async def run(self, **kwargs: Any) -> ToolResult:
        if not self.config.get("enabled", False):
            return ToolResult(ok=False, error="ShellTool is disabled.")

        command = kwargs.get("command")
        if not command or not isinstance(command, str):
            return ToolResult(ok=False, error="ShellTool requires a command string.")

        allowed_commands = set(self.config.get("allowed_commands", []))
        command_parts = shlex.split(command)
        if not command_parts or command_parts[0] not in allowed_commands:
            return ToolResult(ok=False, error=f"Command not allowed: {command_parts[:1]}")

        process = await asyncio.create_subprocess_exec(
            *command_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return ToolResult(
            ok=process.returncode == 0,
            data={"stdout": stdout.decode(), "stderr": stderr.decode(), "returncode": process.returncode},
            error=None if process.returncode == 0 else stderr.decode(),
        )
