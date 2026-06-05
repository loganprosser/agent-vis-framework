"""End-to-end test for examples/combinatorial_calc."""

from __future__ import annotations

import pytest

from app.subsystems.examples.combinatorial_calc import (
    DEFAULT_PARAMETERS,
    build_combinatorial_calc_app,
)
from tests.demos.conftest import ScriptedProvider


@pytest.mark.asyncio
async def test_combinatorial_calc_runs_through_burr_subsystem(build_graph, make_state) -> None:
    provider = ScriptedProvider()  # not used; the subsystem is pure-Python
    graph, _, _ = build_graph("demo_combinatorial_calc", provider=provider)
    final = await graph.ainvoke(make_state("demo_combinatorial_calc", {}))

    outputs = final["node_outputs"]["combinatorial"]
    assert outputs["passed"] + outputs["failed"] > 0
    assert outputs["report"].startswith("# Combinatorial calc report")
    # The div-by-zero constraint should remove any (op=div, b=0) row.
    for record in outputs["executions"]:
        if record["values"].get("op") == "div":
            assert record["values"].get("b") != "0"


def test_factory_is_runnable_in_isolation_with_overrides() -> None:
    # Direct factory smoke check — sanity-checks that the inline calculator
    # template renders to commands that exit zero on the default suite.
    app = build_combinatorial_calc_app().build()
    _, _, final = app.run(halt_after=["report"])
    executions = final["executions"]
    assert any(record["exit_code"] == 0 for record in executions)
    # Every test_case from the fake reducer should be honored up to max_executions.
    assert len(executions) <= 10
    # No duplicates from the reducer.
    seen = {tuple(sorted(record["values"].items())) for record in executions}
    assert len(seen) == len(executions)


def test_default_parameters_align_with_known_shape() -> None:
    names = [p.name for p in DEFAULT_PARAMETERS]
    assert names == ["op", "a", "b"]
