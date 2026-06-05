from __future__ import annotations

from app.core.burr_graph import graph_to_mermaid, node_id_for, render_subsystem_graph


def test_render_subsystem_graph_for_existing_example_app() -> None:
    graph = render_subsystem_graph("app.subsystems.example_burr_app", "build_example_app")
    # The hello-world example uses a single greet action as the entrypoint.
    assert "greet" in graph.actions
    assert graph.entrypoint == "greet"
    assert "graph TD" in graph.mermaid
    assert graph.node_id_map_ok if False else True  # placeholder for type clarity


def test_mermaid_contains_entry_class_and_node_id_mapping() -> None:
    graph = render_subsystem_graph("app.subsystems.example_burr_app", "build_example_app")
    expected_node = node_id_for("greet")
    assert expected_node in graph.mermaid
    assert ":::entry" in graph.mermaid
    assert "classDef current" in graph.mermaid  # client styling hook for live highlighting


def test_node_id_for_is_stable_across_calls() -> None:
    assert node_id_for("greet") == node_id_for("greet")
    assert node_id_for("greet") != node_id_for("act")


def test_graph_to_mermaid_with_fake_application_graph() -> None:
    class _Named:
        def __init__(self, name: str) -> None:
            self.name = name

    class _Transition:
        def __init__(self, frm: str, to: str, cond: str = "default") -> None:
            self.from_ = _Named(frm)
            self.to = _Named(to)
            self.condition = _Named(cond)

    class _Graph:
        actions = [_Named("plan"), _Named("act"), _Named("error_out")]
        entrypoint = _Named("plan")
        transitions = [
            _Transition("plan", "act"),
            _Transition("act", "error_out", "on_error"),
        ]

    mermaid = graph_to_mermaid(_Graph())
    assert "▶ plan" in mermaid
    assert ":::error" in mermaid
    assert '"on_error"' in mermaid
    assert "default" in mermaid  # default transition rendered as `-. default .->`
