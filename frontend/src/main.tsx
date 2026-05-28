import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactFlow, {
  Background,
  Connection,
  Controls,
  Edge,
  MarkerType,
  MiniMap,
  Node,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from "reactflow";
import "reactflow/dist/style.css";
import "./styles.css";
import type { Workflow, WorkflowNode } from "./types";

const api = async <T,>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
};

function toFlowNodes(workflow: Workflow): Node[] {
  return workflow.nodes.map((node, index) => ({
    id: node.id,
    position: {
      x: Number(node.config?.ui?.x ?? 120 + index * 320),
      y: Number(node.config?.ui?.y ?? 240),
    },
    data: {
      label: (
        <div className="flow-node">
          <strong>{node.id}</strong>
          <span>{node.type} · {node.provider ?? "default"}</span>
        </div>
      ),
    },
    type: "default",
  }));
}

function toFlowEdges(workflow: Workflow): Edge[] {
  return workflow.edges.map((edge, index) => ({
    id: `${edge.source}->${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.label || `${edge.source} -> ${edge.target}`,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
}

function fromFlow(workflow: Workflow, nodes: Node[], edges: Edge[]): Workflow {
  const nodePositions = Object.fromEntries(nodes.map((node) => [node.id, node.position]));
  return {
    ...workflow,
    nodes: workflow.nodes.map((node) => ({
      ...node,
      config: {
        ...node.config,
        ui: nodePositions[node.id] ?? node.config.ui,
      },
    })),
    edges: edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      label: typeof edge.label === "string" ? edge.label : undefined,
    })),
  };
}

function App() {
  const [workflowNames, setWorkflowNames] = useState<string[]>([]);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [status, setStatus] = useState("Loading...");

  const selectedWorkflow = workflow?.name ?? "";

  const loadWorkflow = useCallback(async (name: string) => {
    const loaded = await api<Workflow>(`/workflows/${name}`);
    setWorkflow(loaded);
    setNodes(toFlowNodes(loaded));
    setEdges(toFlowEdges(loaded));
    setStatus(`Loaded ${name}`);
  }, []);

  useEffect(() => {
    api<{ workflows: string[] }>("/workflows")
      .then(async (data) => {
        setWorkflowNames(data.workflows);
        await loadWorkflow(data.workflows.includes("starter_three_node") ? "starter_three_node" : data.workflows[0]);
      })
      .catch((error) => setStatus(error.message));
  }, [loadWorkflow]);

  const currentWorkflow = useMemo(() => {
    if (!workflow) return null;
    return fromFlow(workflow, nodes, edges);
  }, [workflow, nodes, edges]);

  const save = async () => {
    if (!currentWorkflow) return;
    await api(`/workflows/${currentWorkflow.name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentWorkflow),
    });
    setStatus(`Saved ${currentWorkflow.name}`);
  };

  const run = async () => {
    if (!currentWorkflow) return;
    const result = await api<{ status: string; run_id: string }>(`/workflows/${currentWorkflow.name}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs: {} }),
    });
    setStatus(`Run ${result.status}: ${result.run_id}`);
  };

  const onConnect = useCallback(
    (connection: Connection) => setEdges((current) => addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, current)),
    [],
  );

  const addNode = () => {
    if (!workflow) return;
    const id = `node_${workflow.nodes.length + 1}`;
    const newNode: WorkflowNode = {
      id,
      type: "doc_reader",
      provider: "mock",
      model: "mock-deterministic",
      system_prompt: "",
      input_keys: [],
      output_keys: [],
      tools: [],
      retry_policy: { max_attempts: 1, backoff_seconds: 0 },
      human_approval: false,
      config: { ui: { x: 160, y: 160 } },
    };
    const updated = { ...workflow, nodes: [...workflow.nodes, newNode] };
    setWorkflow(updated);
    setNodes(toFlowNodes(updated));
  };

  return (
    <main className="app">
      <aside>
        <h1>Agentic Workflow Editor</h1>
        <p>{status}</p>
        <select value={selectedWorkflow} onChange={(event) => loadWorkflow(event.target.value)}>
          {workflowNames.map((name) => <option key={name}>{name}</option>)}
        </select>
        <button onClick={run}>Run</button>
        <button onClick={save}>Save</button>
        <button onClick={addNode}>Add Node</button>
      </aside>
      <section>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={(changes) => setNodes((current) => applyNodeChanges(changes, current))}
          onEdgesChange={(changes) => setEdges((current) => applyEdgeChanges(changes, current))}
          onConnect={onConnect}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ReactFlowProvider>
      <App />
    </ReactFlowProvider>
  </React.StrictMode>,
);
