from __future__ import annotations

import socket
from pathlib import Path

import pytest

from app.services.litellm_lifecycle import LiteLLMSupervisor


def test_base_url_format(tmp_path: Path) -> None:
    cfg = tmp_path / "litellm-config.yaml"
    cfg.write_text("model_list: []\n")
    sup = LiteLLMSupervisor(config_path=str(cfg), host="127.0.0.1", port=4321)
    assert sup.base_url == "http://127.0.0.1:4321/v1"


def test_start_raises_when_config_missing(tmp_path: Path) -> None:
    sup = LiteLLMSupervisor(config_path=str(tmp_path / "missing.yaml"))
    with pytest.raises(FileNotFoundError):
        sup.start()


def test_is_port_open_false_when_nothing_listening() -> None:
    # Bind a socket briefly, then close it so the port is definitely free.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    sup = LiteLLMSupervisor(config_path="ignored", port=port)
    assert sup.is_port_open() is False
