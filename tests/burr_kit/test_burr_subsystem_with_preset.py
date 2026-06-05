from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config_loader import ConfigLoader
from app.core.graph_builder import GraphBuilder
from app.core.registry import ModelRegistry, ToolRegistry
from app.core.state import initial_state
from app.schemas.workflow import ModelProviderConfig


@pytest.fixture()
def configured_dir(tmp_path: Path, monkeypatch) -> Path:
    """Stand up a configs/ tree wired up for the burr_kit_demo workflow."""

    src = Path("configs")
    (tmp_path / "configs").mkdir()
    dst = tmp_path / "configs"

    for name in ("models.yaml", "tools.yaml", "mcps.yaml"):
        (dst / name).write_text((src / name).read_text())

    (dst / "workflows").mkdir()
    (dst / "workflows" / "burr_kit_demo.yaml").write_text(
        (src / "workflows" / "burr_kit_demo.yaml").read_text()
    )

    presets_src = src / "presets" / "example_strict"
    presets_dst = dst / "presets" / "example_strict"
    presets_dst.mkdir(parents=True)
    for f in presets_src.iterdir():
        (presets_dst / f.name).write_text(f.read_text())

    monkeypatch.setenv("WORKFLOW_CONFIG_DIR", str(dst))
    return dst


@pytest.mark.asyncio
async def test_burr_subsystem_runs_with_preset_and_prompt_dir(configured_dir: Path) -> None:
    loader = ConfigLoader(config_dir=configured_dir)
    workflow = loader.load_workflow("burr_kit_demo")
    models = ModelRegistry()
    models.register_provider_config(
        ModelProviderConfig.model_validate(
            {"id": "mock", "type": "mock", "default_model": "mock-1", "config": {}}
        )
    )
    builder = GraphBuilder(models, ToolRegistry(), config_loader=loader)
    graph = builder.compile(workflow)

    state = initial_state(
        run_id="r1",
        workflow_name="burr_kit_demo",
        inputs={"task": "hello"},
    )
    final = await graph.ainvoke(state)

    outputs = final["node_outputs"]["two_step"]
    # End-to-end: both Burr actions ran, the AgentRunner was injected (mock
    # provider returns its deterministic JSON), and the preset/prompt_dir
    # were resolved without error.
    assert outputs["plan"] and outputs["answer"]
    assert "summary" in outputs["plan"]  # mock JSON payload sentinel
    assert "summary" in outputs["answer"]
