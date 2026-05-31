import re

import pytest

from app.models.mock_provider import MockModelProvider
from app.nodes.subsystem import BaseSubsystemNode
from app.schemas.workflow import NodeConfig


class ExampleSubsystemNode(BaseSubsystemNode):
    pass


def build_node() -> ExampleSubsystemNode:
    return ExampleSubsystemNode(
        config=NodeConfig(id="example_subsystem", type="example_subsystem"),
        model_provider=MockModelProvider("mock", "mock-deterministic"),
    )


def test_maps_parent_workflow_inputs_into_subsystem_inputs() -> None:
    node = build_node()

    result = node.map_inputs(
        {
            "inputs": {"message": "hello"},
            "node_outputs": {"prepare": {"count": 3}},
        },
        {
            "child_message": "inputs.message",
            "child_count": "node_outputs.prepare.count",
        },
    )

    assert result == {"child_message": "hello", "child_count": 3}


def test_maps_subsystem_outputs_into_parent_node_outputs() -> None:
    node = build_node()

    result = node.map_outputs(
        {"result": {"summary": "done"}, "status": "complete"},
        {"report": "result.summary", "child_status": "status"},
    )

    assert result == {"report": "done", "child_status": "complete"}


@pytest.mark.parametrize(
    ("method", "data", "value_map", "message"),
    [
        (
            "map_inputs",
            {"inputs": {}},
            {"child_message": "inputs.message"},
            "subsystem node 'example_subsystem' could not map input 'child_message': "
            "parent workflow path 'inputs.message' was not found.",
        ),
        (
            "map_outputs",
            {"result": {}},
            {"report": "result.summary"},
            "subsystem node 'example_subsystem' could not map output 'report': "
            "subsystem final state path 'result.summary' was not found.",
        ),
    ],
)
def test_mapping_helpers_report_missing_paths(method, data, value_map, message) -> None:
    node = build_node()

    with pytest.raises(RuntimeError, match=re.escape(message)):
        getattr(node, method)(data, value_map)
