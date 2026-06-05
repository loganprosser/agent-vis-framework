"""Optional supervisor for a locally-managed LiteLLM proxy.

This module provides a small ``LiteLLMSupervisor`` class that can spawn and
stop a ``litellm`` process from inside agent-vis. It is opt-in: nothing here
runs unless callers explicitly invoke it.

Typical use:
    supervisor = LiteLLMSupervisor(config_path="litellm-config.yaml", port=4000)
    supervisor.start()
    ...
    supervisor.stop()
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LiteLLMSupervisor:
    config_path: str
    port: int = 4000
    host: str = "127.0.0.1"
    extra_env: dict[str, str] | None = None
    startup_timeout: float = 15.0
    _process: subprocess.Popen[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    def is_port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex((self.host, self.port)) == 0

    def is_healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://{self.host}:{self.port}/health/liveliness", timeout=1.0) as resp:
                return 200 <= resp.status < 500
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            return self.is_port_open()

    def start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        if not Path(self.config_path).exists():
            raise FileNotFoundError(f"LiteLLM config not found: {self.config_path}")
        env = os.environ.copy()
        if self.extra_env:
            env.update(self.extra_env)
        self._process = subprocess.Popen(
            [
                "litellm",
                "--config",
                self.config_path,
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self.is_healthy():
                return
            if self._process.poll() is not None:
                raise RuntimeError("litellm process exited before becoming healthy")
            time.sleep(0.25)
        self.stop()
        raise TimeoutError(f"litellm did not become healthy within {self.startup_timeout}s")

    def stop(self) -> None:
        proc = self._process
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._process = None
