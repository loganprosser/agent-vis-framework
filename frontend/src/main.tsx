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
import type {
  BurrAction,
  BurrSubsystemConfig,
  BurrTopology,
  RunEvent,
  RunRecord,
  SubsystemRunMetadata,
  Workflow,
  WorkflowNode,
} from "./types";

const api = async <T,>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
};

const getRun = (runId: string) => api<RunRecord>(`/runs/${encodeURIComponent(runId)}`);
const getRunEvents = (runId: string) => api<RunEvent[]>(`/runs/${encodeURIComponent(runId)}/events`);
const terminalRunStatuses = new Set(["completed", "failed"]);
const csv = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
const csvValue = (value?: string[]) => (value ?? []).join(", ");
const uniqueId = (prefix: string, ids: string[]) => {
  let index = 1;
  while (ids.includes(`${prefix}_${index}`)) index += 1;
  return `${prefix}_${index}`;
};

function subsystemConfig(node: WorkflowNode): BurrSubsystemConfig {
  return node.config as unknown as BurrSubsystemConfig;
}

function defaultTopology(): BurrTopology {
  return {
    entrypoint: "action_1",
    actions: [{ id: "action_1", label: "First action", kind: "agent", reads: [], writes: [] }],
    transitions: [],
  };
}

function defaultBurrNode(id: string): WorkflowNode {
  return {
    id,
    type: "burr_subsystem",
    provider: "mock",
    model: "mock-deterministic",
    system_prompt: "",
    input_keys: ["message"],
    output_keys: ["greeting", "status"],
    tools: [],
    retry_policy: { max_attempts: 1, backoff_seconds: 0 },
    human_approval: false,
    config: {
      app_module: "app.subsystems.example_burr_app",
      app_factory: "build_example_app",
      input_map: { message: "inputs.message" },
      output_map: { greeting: "greeting", status: "status" },
      halt_after: ["greet"],
      fail_on_error: true,
      topology: {
        entrypoint: "greet",
        actions: [
          {
            id: "greet",
            label: "Create greeting",
            kind: "agent",
            description: "Build a greeting from the parent workflow input.",
            reads: ["message"],
            writes: ["greeting", "status"],
          },
        ],
        transitions: [],
      },
      ui: { x: 180, y: 240 },
    },
  };
}

type RuntimeStatus = "pending" | "running" | "completed" | "failed";

type NodeRuntimeState = {
  status: RuntimeStatus;
  subsystemStatus?: RuntimeStatus;
  currentBurrAction?: string;
  burrActionEvents: RunEvent[];
};

const emptyRuntimeState = (): NodeRuntimeState => ({ status: "pending", burrActionEvents: [] });

const sortedEvents = (events: RunEvent[]) => [...events].sort(
  (left, right) => left.timestamp.localeCompare(right.timestamp) || left.id - right.id,
);

const eventAction = (event: RunEvent) => {
  const action = event.payload.action;
  return typeof action === "string" ? action : undefined;
};

function deriveRuntimeByNode(workflow: Workflow | null, events: RunEvent[]) {
  const runtimeByNode: Record<string, NodeRuntimeState> = {};
  for (const node of workflow?.nodes ?? []) runtimeByNode[node.id] = emptyRuntimeState();

  for (const event of sortedEvents(events)) {
    if (!event.node_id || !runtimeByNode[event.node_id]) continue;
    const runtime = runtimeByNode[event.node_id];
    switch (event.event_type) {
      case "node_started":
        runtime.status = "running";
        break;
      case "node_completed":
        runtime.status = "completed";
        break;
      case "node_failed":
        runtime.status = "failed";
        break;
      case "burr_subsystem_started":
        runtime.subsystemStatus = "running";
        break;
      case "burr_subsystem_completed":
        runtime.subsystemStatus = "completed";
        runtime.currentBurrAction = undefined;
        break;
      case "burr_subsystem_failed":
        runtime.subsystemStatus = "failed";
        runtime.currentBurrAction = undefined;
        break;
      case "burr_action_started":
        runtime.burrActionEvents.push(event);
        runtime.currentBurrAction = eventAction(event);
        break;
      case "burr_action_completed":
        runtime.burrActionEvents.push(event);
        if (runtime.currentBurrAction === eventAction(event)) runtime.currentBurrAction = undefined;
        break;
      case "burr_action_failed":
        runtime.burrActionEvents.push(event);
        runtime.subsystemStatus = "failed";
        if (runtime.currentBurrAction === eventAction(event)) runtime.currentBurrAction = undefined;
        break;
    }
  }
  return runtimeByNode;
}

const visibleNodeStatus = (node: WorkflowNode, runtime?: NodeRuntimeState): RuntimeStatus => {
  if (!runtime) return "pending";
  return node.type === "burr_subsystem" ? runtime.subsystemStatus ?? runtime.status : runtime.status;
};

function nodeLabel(node: WorkflowNode, runtime?: NodeRuntimeState) {
  const topology = node.type === "burr_subsystem" ? subsystemConfig(node).topology : undefined;
  const runtimeStatus = visibleNodeStatus(node, runtime);
  return (
    <div className={`flow-node ${node.type === "burr_subsystem" ? "flow-subsystem" : ""}`}>
      {node.type === "burr_subsystem" && <span className="subsystem-label">SUB Burr subsystem</span>}
      <strong>{node.id}</strong>
      <span>{node.type} · {node.provider ?? "default"}</span>
      <span className={`runtime-chip runtime-chip-${runtimeStatus}`}>{runtimeStatus}</span>
      {runtime?.currentBurrAction && <span className="current-action">Burr action: {runtime.currentBurrAction}</span>}
      {topology && <span>{topology.actions.length} internal action{topology.actions.length === 1 ? "" : "s"}</span>}
    </div>
  );
}

function toFlowNodes(workflow: Workflow, runtimeByNode: Record<string, NodeRuntimeState> = {}): Node[] {
  return workflow.nodes.map((node, index) => ({
    id: node.id,
    position: {
      x: Number(node.config?.ui?.x ?? 120 + index * 320),
      y: Number(node.config?.ui?.y ?? 240),
    },
    data: { label: nodeLabel(node, runtimeByNode[node.id]) },
    className: [
      node.type === "burr_subsystem" ? "subsystem-node" : "",
      `runtime-${visibleNodeStatus(node, runtimeByNode[node.id])}`,
    ].filter(Boolean).join(" "),
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
    nodes: workflow.nodes.map((node) => {
      const { subsystem: _subsystem, subsystem_metadata: _subsystemMetadata, ...editableNode } = node;
      return {
        ...editableNode,
        config: {
          ...node.config,
          ui: nodePositions[node.id] ?? node.config.ui,
        },
      };
    }),
    edges: edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      label: typeof edge.label === "string" ? edge.label : undefined,
    })),
  };
}

function JsonMapEditor(props: {
  label: string;
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  setStatus: (value: string) => void;
}) {
  const [text, setText] = useState(JSON.stringify(props.value, null, 2));
  useEffect(() => setText(JSON.stringify(props.value, null, 2)), [props.value]);

  const apply = () => {
    try {
      const parsed = JSON.parse(text) as unknown;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("must be a JSON object");
      }
      if (Object.entries(parsed).some(([key, value]) => !key || typeof value !== "string" || !value)) {
        throw new Error("keys and values must be non-empty strings");
      }
      props.onChange(parsed as Record<string, string>);
      props.setStatus(`${props.label} updated`);
    } catch (error) {
      props.setStatus(`${props.label}: ${(error as Error).message}`);
    }
  };

  return (
    <label className="field">
      <span>{props.label}</span>
      <textarea value={text} onChange={(event) => setText(event.target.value)} onBlur={apply} rows={4} />
    </label>
  );
}

function TagList(props: { label: string; values?: string[] }) {
  return (
    <div className="tag-line">
      <span>{props.label}</span>
      {(props.values ?? []).length
        ? props.values?.map((value) => <code key={value}>{value}</code>)
        : <em>none</em>}
    </div>
  );
}

function RuntimeTimeline(props: { events: RunEvent[]; runId?: string }) {
  const events = useMemo(() => sortedEvents(props.events), [props.events]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const selectedEvent = events.find((event) => event.id === selectedEventId);

  useEffect(() => setSelectedEventId(null), [props.runId]);

  return (
    <div className="timeline-panel">
      <div className="section-heading">
        <h2>Runtime Timeline</h2>
        <span>{events.length} event{events.length === 1 ? "" : "s"}</span>
      </div>
      {!props.runId && <p>Run a workflow to inspect runtime events.</p>}
      {props.runId && events.length === 0 && <p>Waiting for runtime events...</p>}
      <div className="timeline-list">
        {events.map((event) => (
          <button
            className={`${selectedEventId === event.id ? "selected" : ""} ${event.event_type.endsWith("_failed") ? "failed" : ""}`}
            key={event.id}
            onClick={() => setSelectedEventId(event.id)}
          >
            <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
            <strong>{event.event_type}</strong>
            <span>{event.node_id ?? "run"}</span>
          </button>
        ))}
      </div>
      {selectedEvent && (
        <pre className="timeline-payload">{JSON.stringify(selectedEvent.payload, null, 2)}</pre>
      )}
    </div>
  );
}

function TopologyEditor(props: {
  topology?: BurrTopology;
  onChange: (topology: BurrTopology) => void;
  setStatus: (value: string) => void;
}) {
  const [selectedActionId, setSelectedActionId] = useState<string | null>(props.topology?.entrypoint ?? null);
  const topology = props.topology;
  const selectedAction = topology?.actions.find((action) => action.id === selectedActionId);

  useEffect(() => {
    if (topology && !topology.actions.some((action) => action.id === selectedActionId)) {
      setSelectedActionId(topology.entrypoint);
    }
  }, [selectedActionId, topology]);

  if (!topology) {
    return (
      <div className="empty-topology">
        <p>No visualization topology metadata has been declared for this Python factory yet. Creating it does not change runtime behavior.</p>
        <button onClick={() => props.onChange(defaultTopology())}>Create Visualization Topology</button>
      </div>
    );
  }

  const updateAction = (actionId: string, patch: Partial<BurrAction>) => {
    props.onChange({
      ...topology,
      actions: topology.actions.map((action) => action.id === actionId ? { ...action, ...patch } : action),
    });
  };

  const renameAction = (actionId: string, nextId: string) => {
    if (!nextId || topology.actions.some((action) => action.id === nextId && action.id !== actionId)) {
      props.setStatus("Internal action ids must be non-empty and unique.");
      return;
    }
    props.onChange({
      ...topology,
      entrypoint: topology.entrypoint === actionId ? nextId : topology.entrypoint,
      actions: topology.actions.map((action) => action.id === actionId ? { ...action, id: nextId } : action),
      transitions: topology.transitions.map((transition) => ({
        ...transition,
        source: transition.source === actionId ? nextId : transition.source,
        target: transition.target === actionId ? nextId : transition.target,
      })),
    });
    setSelectedActionId(nextId);
  };

  const addAction = () => {
    const id = uniqueId("action", topology.actions.map((action) => action.id));
    props.onChange({
      ...topology,
      actions: [...topology.actions, { id, label: "New action", kind: "agent", reads: [], writes: [] }],
    });
    setSelectedActionId(id);
  };

  const removeAction = (actionId: string) => {
    if (topology.actions.length === 1) {
      props.setStatus("A Burr topology needs at least one action.");
      return;
    }
    const actions = topology.actions.filter((action) => action.id !== actionId);
    props.onChange({
      entrypoint: topology.entrypoint === actionId ? actions[0].id : topology.entrypoint,
      actions,
      transitions: topology.transitions.filter(
        (transition) => transition.source !== actionId && transition.target !== actionId,
      ),
    });
    setSelectedActionId(actions[0].id);
  };

  const addTransition = () => {
    const source = topology.actions[0]?.id;
    const target = topology.actions[1]?.id ?? source;
    if (!source || !target) return;
    props.onChange({
      ...topology,
      transitions: [...topology.transitions, { source, target, condition: "default" }],
    });
  };

  return (
    <div className="topology-editor">
      <div className="section-heading">
        <div>
          <h3>Internal Burr Topology</h3>
          <p>Visualization metadata only. Editing this does not change the Python Burr factory.</p>
        </div>
        <button onClick={addAction}>Add Action</button>
      </div>
      <label className="field">
        <span>Entrypoint</span>
        <select
          value={topology.entrypoint}
          onChange={(event) => props.onChange({ ...topology, entrypoint: event.target.value })}
        >
          {topology.actions.map((action) => <option key={action.id}>{action.id}</option>)}
        </select>
      </label>
      <div className="internal-canvas">
        {topology.actions.map((action) => {
          const outgoing = topology.transitions.filter((transition) => transition.source === action.id);
          return (
            <button
              className={`internal-action ${action.id === selectedActionId ? "selected" : ""}`}
              key={action.id}
              onClick={() => setSelectedActionId(action.id)}
            >
              <small>{action.kind ?? "action"}{action.id === topology.entrypoint ? " · entry" : ""}</small>
              <strong>{action.label || action.id}</strong>
              <span>{action.id}</span>
              {outgoing.length > 0 && <em>{outgoing.length} outgoing transition{outgoing.length === 1 ? "" : "s"}</em>}
            </button>
          );
        })}
      </div>
      {selectedAction && (
        <div className="action-editor">
          <div className="section-heading">
            <h3>Edit Action</h3>
            <button className="danger" onClick={() => removeAction(selectedAction.id)}>Remove</button>
          </div>
          <div className="two-column">
            <label className="field">
              <span>Action ID</span>
              <input value={selectedAction.id} onChange={(event) => renameAction(selectedAction.id, event.target.value)} />
            </label>
            <label className="field">
              <span>Kind</span>
              <select
                value={selectedAction.kind ?? "action"}
                onChange={(event) => updateAction(selectedAction.id, { kind: event.target.value as BurrAction["kind"] })}
              >
                {["agent", "action", "router", "tool", "human"].map((kind) => <option key={kind}>{kind}</option>)}
              </select>
            </label>
          </div>
          <label className="field">
            <span>Label</span>
            <input value={selectedAction.label ?? ""} onChange={(event) => updateAction(selectedAction.id, { label: event.target.value })} />
          </label>
          <label className="field">
            <span>Description</span>
            <textarea value={selectedAction.description ?? ""} onChange={(event) => updateAction(selectedAction.id, { description: event.target.value })} rows={2} />
          </label>
          <div className="two-column">
            <label className="field">
              <span>Reads</span>
              <input value={csvValue(selectedAction.reads)} onChange={(event) => updateAction(selectedAction.id, { reads: csv(event.target.value) })} />
            </label>
            <label className="field">
              <span>Writes</span>
              <input value={csvValue(selectedAction.writes)} onChange={(event) => updateAction(selectedAction.id, { writes: csv(event.target.value) })} />
            </label>
          </div>
          <label className="field">
            <span>Model override</span>
            <input value={selectedAction.model ?? ""} onChange={(event) => updateAction(selectedAction.id, { model: event.target.value || null })} placeholder="Optional" />
          </label>
          <label className="field">
            <span>Prompt / instruction</span>
            <textarea value={selectedAction.prompt ?? ""} onChange={(event) => updateAction(selectedAction.id, { prompt: event.target.value })} rows={3} />
          </label>
          <TagList label="Reads" values={selectedAction.reads} />
          <TagList label="Writes" values={selectedAction.writes} />
        </div>
      )}
      <div className="section-heading">
        <h3>Transitions</h3>
        <button onClick={addTransition}>Add Transition</button>
      </div>
      <div className="transition-list">
        {topology.transitions.length === 0 && <p>No internal transitions. This subsystem can still contain one action.</p>}
        {topology.transitions.map((transition, index) => (
          <div className="transition-row" key={`${transition.source}-${transition.target}-${index}`}>
            <select
              value={transition.source}
              onChange={(event) => props.onChange({
                ...topology,
                transitions: topology.transitions.map((item, itemIndex) => itemIndex === index ? { ...item, source: event.target.value } : item),
              })}
            >
              {topology.actions.map((action) => <option key={action.id}>{action.id}</option>)}
            </select>
            <span>→</span>
            <select
              value={transition.target}
              onChange={(event) => props.onChange({
                ...topology,
                transitions: topology.transitions.map((item, itemIndex) => itemIndex === index ? { ...item, target: event.target.value } : item),
              })}
            >
              {topology.actions.map((action) => <option key={action.id}>{action.id}</option>)}
            </select>
            <input
              value={transition.condition ?? "default"}
              onChange={(event) => props.onChange({
                ...topology,
                transitions: topology.transitions.map((item, itemIndex) => itemIndex === index ? { ...item, condition: event.target.value } : item),
              })}
              placeholder="condition"
            />
            <button
              className="icon-button danger"
              title="Remove transition"
              onClick={() => props.onChange({
                ...topology,
                transitions: topology.transitions.filter((_item, itemIndex) => itemIndex !== index),
              })}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function SubsystemInspector(props: {
  node: WorkflowNode;
  metadata?: SubsystemRunMetadata;
  artifacts: Record<string, unknown>;
  runId?: string;
  runtime?: NodeRuntimeState;
  updateConfig: (patch: Partial<BurrSubsystemConfig>) => void;
  setStatus: (value: string) => void;
}) {
  const config = subsystemConfig(props.node);
  const artifactNames = Object.keys(props.artifacts)
    .filter((name) => name.endsWith(".json"))
    .sort((left, right) => {
      const preferred = ["burr_final_state.json", "burr_trace.json"];
      const leftIndex = preferred.indexOf(left);
      const rightIndex = preferred.indexOf(right);
      if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right);
      if (leftIndex === -1) return 1;
      if (rightIndex === -1) return -1;
      return leftIndex - rightIndex;
    });
  const recentActionEvents = (props.runtime?.burrActionEvents ?? []).slice(-10).reverse();
  const recentActionSequence = (props.runtime?.burrActionEvents ?? [])
    .filter((event) => event.event_type !== "burr_action_started")
    .slice(-10)
    .map((event) => eventAction(event) ?? "unknown action");
  const haltMode = config.terminal_states ? "terminal_states" : "halt_after";
  const haltValues = config.terminal_states ?? config.halt_after ?? [];
  const runtimeStatus = visibleNodeStatus(props.node, props.runtime);

  return (
    <div className="inspector-content">
      <div className="subsystem-banner">
        <strong>SUB Burr Subsystem</strong>
        <span>Internal runtime node</span>
      </div>
      <dl className="summary-grid">
        <dt>Node ID</dt><dd>{props.node.id}</dd>
        <dt>Node type</dt><dd>{props.node.type}</dd>
        <dt>Status</dt><dd>{runtimeStatus}</dd>
        <dt>Current action</dt><dd>{props.runtime?.currentBurrAction ?? "Not running"}</dd>
        <dt>Terminal state</dt><dd>{props.metadata?.terminal_state ?? "Not available"}</dd>
        <dt>Halt reason</dt><dd>{props.metadata?.halt_reason ?? "Not available"}</dd>
      </dl>
      <div className="notice">
        Internal topology is visualization metadata only. Runtime execution still comes from the Python factory.
      </div>
      <div className="two-column">
        <label className="field">
          <span>App module</span>
          <input value={config.app_module} onChange={(event) => props.updateConfig({ app_module: event.target.value })} />
        </label>
        <label className="field">
          <span>App factory</span>
          <input value={config.app_factory} onChange={(event) => props.updateConfig({ app_factory: event.target.value })} />
        </label>
      </div>
      <JsonMapEditor label="Input map" value={config.input_map} onChange={(input_map) => props.updateConfig({ input_map })} setStatus={props.setStatus} />
      <JsonMapEditor label="Output map" value={config.output_map} onChange={(output_map) => props.updateConfig({ output_map })} setStatus={props.setStatus} />
      <div className="two-column">
        <label className="field">
          <span>Stop mode</span>
          <select
            value={haltMode}
            onChange={(event) => event.target.value === "terminal_states"
              ? props.updateConfig({ halt_after: undefined, terminal_states: haltValues })
              : props.updateConfig({ terminal_states: undefined, halt_after: haltValues })}
          >
            <option value="halt_after">Halt after action</option>
            <option value="terminal_states">Terminal states</option>
          </select>
        </label>
        <label className="field">
          <span>{haltMode === "terminal_states" ? "Terminal states" : "Halt after actions"}</span>
          <input
            value={csvValue(haltValues)}
            onChange={(event) => haltMode === "terminal_states"
              ? props.updateConfig({ terminal_states: csv(event.target.value) })
              : props.updateConfig({ halt_after: csv(event.target.value) })}
          />
        </label>
      </div>
      <div className="two-column">
        <label className="field">
          <span>Artifact alias</span>
          <input value={config.artifact_name ?? "burr_final_state"} onChange={(event) => props.updateConfig({ artifact_name: event.target.value })} />
        </label>
        <label className="field">
          <span>Timeout seconds</span>
          <input
            type="number"
            min="0"
            value={config.timeout_seconds ?? ""}
            onChange={(event) => props.updateConfig({ timeout_seconds: event.target.value ? Number(event.target.value) : undefined })}
            placeholder="Optional"
          />
        </label>
      </div>
      <label className="check-field">
        <input type="checkbox" checked={config.fail_on_error ?? true} onChange={(event) => props.updateConfig({ fail_on_error: event.target.checked })} />
        <span>Fail parent workflow when the Burr subsystem errors</span>
      </label>
      <TopologyEditor topology={config.topology} onChange={(topology) => props.updateConfig({ topology })} setStatus={props.setStatus} />
      <div className="runtime-panel">
        <h3>Runtime Artifacts</h3>
        <div className="artifact-list">
          {artifactNames.length && props.runId
            ? artifactNames.map((name) => (
                <a
                  key={name}
                  href={`/runs/${encodeURIComponent(props.runId!)}/artifacts/${encodeURIComponent(props.node.id)}/${encodeURIComponent(name)}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {name}
                </a>
              ))
            : <span>Run this workflow to inspect Burr state and trace artifacts.</span>}
        </div>
        <h3>Recent Burr Action Sequence</h3>
        <div className="action-sequence">
          {recentActionSequence.length
            ? recentActionSequence.map((action, index) => <code key={`${action}-${index}`}>{action}</code>)
            : <span>No completed internal Burr actions recorded yet.</span>}
        </div>
        <h3>Recent Burr Action Events</h3>
        <div className="action-event-list">
          {recentActionEvents.length
            ? recentActionEvents.map((event) => (
                <div key={event.id}>
                  <code>{eventAction(event) ?? "unknown action"}</code>
                  <span>{event.event_type.replace("burr_action_", "")}</span>
                </div>
              ))
            : <span>No internal Burr actions recorded yet.</span>}
        </div>
        <h3>_subsystems.{props.node.id} Metadata</h3>
        {props.metadata && <pre>{JSON.stringify(props.metadata, null, 2)}</pre>}
        {!props.metadata && <span className="subtle">Run this workflow to inspect subsystem metadata.</span>}
      </div>
    </div>
  );
}

function App() {
  const [workflowNames, setWorkflowNames] = useState<string[]>([]);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [status, setStatus] = useState("Loading...");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [runRecord, setRunRecord] = useState<RunRecord | null>(null);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [runInput, setRunInput] = useState('{\n  "inputs": {}\n}');
  const runtimeByNode = useMemo(() => deriveRuntimeByNode(workflow, runEvents), [workflow, runEvents]);

  const loadWorkflow = useCallback(async (name: string) => {
    try {
      const loaded = await api<Workflow>(`/workflows/${name}`);
      setWorkflow(loaded);
      setNodes(toFlowNodes(loaded));
      setEdges(toFlowEdges(loaded));
      setSelectedNodeId(loaded.nodes[0]?.id ?? null);
      setRunRecord(null);
      setRunEvents([]);
      setStatus(`Loaded ${name}`);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }, []);

  useEffect(() => {
    api<{ workflows: string[] }>("/workflows")
      .then(async (data) => {
        setWorkflowNames(data.workflows);
        const initial = data.workflows.includes("starter_three_node") ? "starter_three_node" : data.workflows[0];
        if (initial) await loadWorkflow(initial);
      })
      .catch((error) => setStatus(error.message));
  }, [loadWorkflow]);

  useEffect(() => {
    const runId = runRecord?.run_id;
    if (!runId) return;
    let cancelled = false;

    const refresh = async () => {
      try {
        const active = !terminalRunStatuses.has(runRecord.status);
        const [events, latestRun] = await Promise.all([
          getRunEvents(runId),
          active ? getRun(runId) : Promise.resolve(null),
        ]);
        if (cancelled) return;
        setRunEvents(sortedEvents(events));
        if (latestRun) setRunRecord(latestRun);
      } catch (error) {
        if (!cancelled) setStatus(`Runtime refresh failed: ${(error as Error).message}`);
      }
    };

    void refresh();
    if (terminalRunStatuses.has(runRecord.status)) return () => { cancelled = true; };
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runRecord?.run_id, runRecord?.status]);

  useEffect(() => {
    if (!workflow) return;
    const workflowNodes = new Map(workflow.nodes.map((node) => [node.id, node]));
    setNodes((current) => current.map((flowNode) => {
      const workflowNode = workflowNodes.get(flowNode.id);
      return workflowNode
        ? {
            ...flowNode,
            className: [
              workflowNode.type === "burr_subsystem" ? "subsystem-node" : "",
              `runtime-${visibleNodeStatus(workflowNode, runtimeByNode[workflowNode.id])}`,
            ].filter(Boolean).join(" "),
            data: { label: nodeLabel(workflowNode, runtimeByNode[workflowNode.id]) },
          }
        : flowNode;
    }));
  }, [runtimeByNode, workflow]);

  const currentWorkflow = useMemo(() => workflow ? fromFlow(workflow, nodes, edges) : null, [workflow, nodes, edges]);
  const selectedNode = workflow?.nodes.find((node) => node.id === selectedNodeId);
  const subsystemMetadata = selectedNode ? runRecord?.state?._subsystems?.[selectedNode.id] : undefined;
  const subsystemArtifacts = selectedNode ? runRecord?.state?.artifacts?.[selectedNode.id] ?? {} : {};
  const selectedNodeRuntime = selectedNode ? runtimeByNode[selectedNode.id] : undefined;

  const replaceWorkflow = (nextWorkflow: Workflow, selectId?: string | null) => {
    setWorkflow(nextWorkflow);
    setNodes(toFlowNodes(nextWorkflow));
    setEdges(toFlowEdges(nextWorkflow));
    if (selectId !== undefined) setSelectedNodeId(selectId);
  };

  const updateSelectedNode = (update: (node: WorkflowNode) => WorkflowNode) => {
    if (!selectedNodeId) return;
    setWorkflow((current) => current
      ? { ...current, nodes: current.nodes.map((node) => node.id === selectedNodeId ? update(node) : node) }
      : current);
  };

  const updateSubsystemConfig = (patch: Partial<BurrSubsystemConfig>) => {
    updateSelectedNode((node) => ({ ...node, config: { ...node.config, ...patch } }));
  };

  const save = async () => {
    if (!currentWorkflow) return;
    try {
      await api(`/workflows/${currentWorkflow.name}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentWorkflow),
      });
      setStatus(`Saved ${currentWorkflow.name}`);
    } catch (error) {
      setStatus(`Save failed: ${(error as Error).message}`);
    }
  };

  const run = async () => {
    if (!currentWorkflow) return;
    try {
      const body = JSON.parse(runInput) as { inputs?: Record<string, unknown> };
      setRunRecord(null);
      setRunEvents([]);
      setStatus(`Running ${currentWorkflow.name}...`);
      const result = await api<RunRecord>(`/workflows/${currentWorkflow.name}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setRunRecord(result);
      setStatus(`Run ${result.status}: ${result.run_id}`);
    } catch (error) {
      setStatus(`Run failed: ${(error as Error).message}`);
    }
  };

  const onConnect = useCallback(
    (connection: Connection) => setEdges((current) => addEdge({ ...connection, markerEnd: { type: MarkerType.ArrowClosed } }, current)),
    [],
  );

  const addNode = (type: "normal" | "burr") => {
    if (!currentWorkflow) return;
    const id = uniqueId(type === "burr" ? "burr_subsystem" : "node", currentWorkflow.nodes.map((node) => node.id));
    const newNode: WorkflowNode = type === "burr"
      ? defaultBurrNode(id)
      : {
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
    replaceWorkflow({ ...currentWorkflow, nodes: [...currentWorkflow.nodes, newNode] }, id);
  };

  const deleteSelectedNode = () => {
    if (!currentWorkflow || !selectedNodeId || currentWorkflow.nodes.length === 1) return;
    const nodes = currentWorkflow.nodes.filter((node) => node.id !== selectedNodeId);
    replaceWorkflow({
      ...currentWorkflow,
      entrypoint: currentWorkflow.entrypoint === selectedNodeId ? nodes[0].id : currentWorkflow.entrypoint,
      nodes,
      edges: currentWorkflow.edges.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId),
    }, nodes[0].id);
  };

  return (
    <main className="app-shell">
      <aside className="left-panel">
        <div>
          <span className="eyebrow">Workflow Studio</span>
          <h1>Agentic Editor</h1>
          <p className="status">{status}</p>
        </div>
        <label className="field">
          <span>Workflow</span>
          <select value={workflow?.name ?? ""} onChange={(event) => loadWorkflow(event.target.value)}>
            {workflowNames.map((name) => <option key={name}>{name}</option>)}
          </select>
        </label>
        <div className="button-row">
          <button className="primary" onClick={save}>Save</button>
          <button onClick={run}>Run</button>
        </div>
        <div className="palette">
          <h2>Add Nodes</h2>
          <button onClick={() => addNode("normal")}><strong>+</strong><span>Standard node</span></button>
          <button className="subsystem-add" onClick={() => addNode("burr")}><strong>SUB</strong><span>Burr subsystem</span></button>
        </div>
        <div className="node-list">
          <h2>Workflow Nodes</h2>
          {workflow?.nodes.map((node) => (
            <button className={node.id === selectedNodeId ? "selected" : ""} key={node.id} onClick={() => setSelectedNodeId(node.id)}>
              <span>{node.type === "burr_subsystem" ? "SUB" : "NODE"}</span>
              <strong>{node.id}</strong>
              <small>{node.type}</small>
            </button>
          ))}
        </div>
        <label className="field run-input">
          <span>Run request JSON</span>
          <textarea value={runInput} onChange={(event) => setRunInput(event.target.value)} rows={6} />
        </label>
        {runRecord && (
          <div className="run-summary">
            <h2>Latest Run</h2>
            <strong>{runRecord.status}</strong>
            <code>{runRecord.run_id}</code>
            {runRecord.error && <pre>{runRecord.error}</pre>}
          </div>
        )}
        <RuntimeTimeline events={runEvents} runId={runRecord?.run_id} />
      </aside>
      <section className="canvas-panel">
        <div className="canvas-heading">
          <div>
            <span className="eyebrow">Parent Workflow</span>
            <h2>{workflow?.name ?? "Loading workflow..."}</h2>
          </div>
          <span>Drag nodes and connect handles to shape the outer workflow.</span>
        </div>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={(changes) => setNodes((current) => applyNodeChanges(changes, current))}
          onEdgesChange={(changes) => setEdges((current) => applyEdgeChanges(changes, current))}
          onConnect={onConnect}
          onNodeClick={(_event, node) => setSelectedNodeId(node.id)}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </section>
      <aside className="right-panel">
        <div className="inspector-heading">
          <span className="eyebrow">Inspector</span>
          <h2>{selectedNode?.id ?? "Select a node"}</h2>
        </div>
        {!selectedNode && <p>Select a node to edit its configuration.</p>}
        {selectedNode?.type === "burr_subsystem" && (
          <SubsystemInspector
            node={selectedNode}
            metadata={subsystemMetadata}
            artifacts={subsystemArtifacts}
            runId={runRecord?.run_id}
            runtime={selectedNodeRuntime}
            updateConfig={updateSubsystemConfig}
            setStatus={setStatus}
          />
        )}
        {selectedNode && selectedNode.type !== "burr_subsystem" && (
          <div className="inspector-content">
            <dl className="summary-grid">
              <dt>Node ID</dt><dd>{selectedNode.id}</dd>
              <dt>Node type</dt><dd>{selectedNode.type}</dd>
              <dt>Status</dt><dd>{visibleNodeStatus(selectedNode, selectedNodeRuntime)}</dd>
              <dt>Provider</dt><dd>{selectedNode.provider ?? "default"}</dd>
              <dt>Model</dt><dd>{selectedNode.model ?? "default"}</dd>
            </dl>
            <p className="notice">Standard node editing remains available in the built-in editor while this React studio expands.</p>
          </div>
        )}
        {selectedNode && workflow && workflow.nodes.length > 1 && (
          <button className="danger delete-node" onClick={deleteSelectedNode}>Delete Selected Node</button>
        )}
      </aside>
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
