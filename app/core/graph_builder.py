from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.core.config_loader import ConfigLoader
from app.core.registry import ModelRegistry, NodeRegistry, ToolRegistry
from app.core.runtime_events import RuntimeEventStore
from app.core.state import WorkflowState
from app.nodes.burr_subsystem import BurrSubsystemNode
from app.nodes.constraint_builder import ConstraintBuilderNode
from app.nodes.problem_analyzer import ProblemAnalyzerNode
from app.nodes.solution_presenter import SolutionPresenterNode
from app.nodes.doc_reader import DocReaderNode
from app.nodes.domain_generator import DomainGeneratorNode
from app.nodes.mcp_call import McpCallNode
from app.nodes.mcp_discovery import McpDiscoveryNode
from app.nodes.mock_requirements_input import MockRequirementsInputNode
from app.nodes.report_generator import ReportGeneratorNode
from app.nodes.requirements_report import RequirementsReportNode
from app.nodes.source_reader import SourceReaderNode
from app.nodes.test_runner import TestRunnerNode
from app.nodes.test_validator import TestValidatorNode
from app.nodes.test_writer import TestWriterNode
from app.nodes.tnt_cli_reducer import TntCliReducerNode
from app.nodes.variable_classifier import VariableClassifierNode
from app.nodes.variable_extractor import VariableExtractorNode
from app.schemas.workflow import WorkflowConfig
from app.tools.base import ObservableTool


def default_node_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("burr_subsystem", BurrSubsystemNode)
    registry.register("doc_reader", DocReaderNode)
    registry.register("source_reader", SourceReaderNode)
    registry.register("variable_extractor", VariableExtractorNode)
    registry.register("variable_classifier", VariableClassifierNode)
    registry.register("domain_generator", DomainGeneratorNode)
    registry.register("mcp_discovery", McpDiscoveryNode)
    registry.register("mcp_call", McpCallNode)
    registry.register("mock_requirements_input", MockRequirementsInputNode)
    registry.register("constraint_builder", ConstraintBuilderNode)
    registry.register("tnt_cli_reducer", TntCliReducerNode)
    registry.register("test_writer", TestWriterNode)
    registry.register("test_validator", TestValidatorNode)
    registry.register("test_runner", TestRunnerNode)
    registry.register("report_generator", ReportGeneratorNode)
    registry.register("requirements_report", RequirementsReportNode)
    registry.register("problem_analyzer", ProblemAnalyzerNode)
    registry.register("solution_presenter", SolutionPresenterNode)
    return registry


class GraphBuilder:
    def __init__(
        self,
        model_registry: ModelRegistry,
        tool_registry: ToolRegistry,
        node_registry: NodeRegistry | None = None,
        config_loader: ConfigLoader | None = None,
        event_store: RuntimeEventStore | None = None,
    ) -> None:
        self.model_registry = model_registry
        self.tool_registry = tool_registry
        self.node_registry = node_registry or default_node_registry()
        self.config_loader = config_loader
        self.event_store = event_store

    def compile(self, workflow: WorkflowConfig):
        graph = StateGraph(WorkflowState)

        for node_config in workflow.nodes:
            effective_config = node_config
            if node_config.system_prompt_file and self.config_loader:
                resolved = self.config_loader.resolve_system_prompt(node_config)
                effective_config = node_config.model_copy(update={
                    "system_prompt": resolved,
                    "system_prompt_file": None,
                })

            tools = self.tool_registry.many(effective_config.tools)
            if self.event_store is not None:
                tools = {
                    tool_id: ObservableTool(
                        tool,
                        node_id=effective_config.id,
                        event_store=self.event_store,
                    )
                    for tool_id, tool in tools.items()
                }

            node = self.node_registry.create(
                effective_config.type,
                config=effective_config,
                model_provider=self.model_registry.get(effective_config.provider),
                tools=tools,
                event_store=self.event_store,
            )
            graph.add_node(effective_config.id, node)

        graph.set_entry_point(workflow.entrypoint)
        sources_with_outgoing_edges: set[str] = set()
        for edge in workflow.edges:
            graph.add_edge(edge.source, edge.target)
            sources_with_outgoing_edges.add(edge.source)

        for node_config in workflow.nodes:
            if node_config.id not in sources_with_outgoing_edges:
                graph.add_edge(node_config.id, END)

        return graph.compile()
