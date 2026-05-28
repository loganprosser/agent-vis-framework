from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.core.registry import ModelRegistry, NodeRegistry, ToolRegistry
from app.core.state import WorkflowState
from app.nodes.constraint_builder import ConstraintBuilderNode
from app.nodes.doc_reader import DocReaderNode
from app.nodes.domain_generator import DomainGeneratorNode
from app.nodes.report_generator import ReportGeneratorNode
from app.nodes.source_reader import SourceReaderNode
from app.nodes.test_runner import TestRunnerNode
from app.nodes.test_validator import TestValidatorNode
from app.nodes.test_writer import TestWriterNode
from app.nodes.tnt_cli_reducer import TntCliReducerNode
from app.nodes.variable_classifier import VariableClassifierNode
from app.nodes.variable_extractor import VariableExtractorNode
from app.schemas.workflow import WorkflowConfig


def default_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("doc_reader", DocReaderNode)
    registry.register("source_reader", SourceReaderNode)
    registry.register("variable_extractor", VariableExtractorNode)
    registry.register("variable_classifier", VariableClassifierNode)
    registry.register("domain_generator", DomainGeneratorNode)
    registry.register("constraint_builder", ConstraintBuilderNode)
    registry.register("tnt_cli_reducer", TntCliReducerNode)
    registry.register("test_writer", TestWriterNode)
    registry.register("test_validator", TestValidatorNode)
    registry.register("test_runner", TestRunnerNode)
    registry.register("report_generator", ReportGeneratorNode)
    return registry


class GraphBuilder:
    def __init__(
        self,
        model_registry: ModelRegistry,
        tool_registry: ToolRegistry,
        node_registry: NodeRegistry | None = None,
    ) -> None:
        self.model_registry = model_registry
        self.tool_registry = tool_registry
        self.node_registry = node_registry or default_node_registry()

    def compile(self, workflow: WorkflowConfig):
        graph = StateGraph(WorkflowState)

        for node_config in workflow.nodes:
            node = self.node_registry.create(
                node_config.type,
                config=node_config,
                model_provider=self.model_registry.get(node_config.provider),
                tools=self.tool_registry.many(node_config.tools),
            )
            graph.add_node(node_config.id, node)

        graph.set_entry_point(workflow.entrypoint)
        sources_with_outgoing_edges: set[str] = set()
        for edge in workflow.edges:
            graph.add_edge(edge.source, edge.target)
            sources_with_outgoing_edges.add(edge.source)

        for node_config in workflow.nodes:
            if node_config.id not in sources_with_outgoing_edges:
                graph.add_edge(node_config.id, END)

        return graph.compile()
