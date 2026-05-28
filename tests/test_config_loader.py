from app.core.config_loader import ConfigLoader


def test_loads_example_workflow() -> None:
    loader = ConfigLoader()
    workflow = loader.load_workflow("combinatorial_test_generation")

    assert workflow.name == "combinatorial_test_generation"
    assert workflow.entrypoint == "doc_reader"
    assert [node.id for node in workflow.nodes][0] == "doc_reader"
    assert workflow.edges[-1].target == "report_generator"
