import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactFlow, {
  Background,
  Connection,
  ConnectionLineType,
  Controls,
  Edge,
  MarkerType,
  MiniMap,
  Node,
  Position,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
} from "reactflow";
import "reactflow/dist/style.css";
import "./styles.css";
import {
  CommonNodeInspector,
  EdgeEditor,
  MarkdownEditor,
  WorkflowJsonEditor,
  WorkflowSettings,
} from "./editor-panels";
import type { PromptTarget } from "./editor-panels";
import type {
  BurrAction,
  BurrSubsystemConfig,
  BurrTopology,
  Catalog,
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
const promptPath = (file: string) => file.split("/").map(encodeURIComponent).join("/");
const savePrompt = async (file: string, content: string): Promise<void> => {
  await api(`/prompts/${promptPath(file)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
};
const emptyCatalog: Catalog = { providers: [], tools: [], mcps: [], node_types: [] };
const terminalRunStatuses = new Set(["completed", "failed"]);
const csv = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
const csvValue = (value?: string[]) => (value ?? []).join(", ");
const slugify = (value: string) => value.trim().replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "node";
const themeStorageKey = "agentic-workflow-editor-theme";
const panelWidthStorageKey = "agentic-workflow-editor-panel-widths";
const defaultPanelWidths = { left: 320, right: 440 };
const minPanelWidths = { left: 240, right: 300 };
const minCanvasWidth = 360;
const panelResizerWidth = 8;
type ColorTheme = "dark" | "light";
type PanelSide = keyof typeof defaultPanelWidths;
type PanelWidths = typeof defaultPanelWidths;
const flowEdgeColor = "#7cb7f5";
const flowEdgeOptions = {
  type: "smoothstep",
  style: { stroke: flowEdgeColor, strokeWidth: 2 },
  markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: flowEdgeColor },
  labelStyle: { fill: "#dbeafe", fontSize: 11, fontWeight: 700 },
  labelBgStyle: { fill: "#111925", fillOpacity: .96, stroke: "#38506d", strokeWidth: 1 },
  labelBgPadding: [7, 4] as [number, number],
  labelBgBorderRadius: 5,
  pathOptions: { borderRadius: 14, offset: 28 },
};

const clamp = (value: number, minimum: number, maximum: number) => Math.min(Math.max(value, minimum), maximum);

function storedTheme(): ColorTheme {
  return window.localStorage.getItem(themeStorageKey) === "light" ? "light" : "dark";
}

function fitPanelWidths(widths: PanelWidths, shellWidth: number): PanelWidths {
  const maxCombinedWidth = shellWidth - minCanvasWidth - panelResizerWidth * 2;
  if (maxCombinedWidth < minPanelWidths.left + minPanelWidths.right) return widths;
  const left = clamp(widths.left, minPanelWidths.left, maxCombinedWidth - minPanelWidths.right);
  const right = clamp(widths.right, minPanelWidths.right, maxCombinedWidth - left);
  return { left, right };
}

function storedPanelWidths(): PanelWidths {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(panelWidthStorageKey) ?? "") as Partial<PanelWidths>;
    if (typeof parsed.left === "number" && typeof parsed.right === "number") {
      return fitPanelWidths({ left: parsed.left, right: parsed.right }, window.innerWidth);
    }
  } catch {
    // Use the defaults when local storage is empty or malformed.
  }
  return fitPanelWidths(defaultPanelWidths, window.innerWidth);
}

const uniqueId = (prefix: string, ids: string[]) => {
  let index = 1;
  while (ids.includes(`${prefix}_${index}`)) index += 1;
  return `${prefix}_${index}`;
};

function draftWorkflow(): Workflow {
  const name = "draft_workflow";
  return {
    name,
    version: "0.1.0",
    description: "A new config-driven workflow.",
    entrypoint: "start",
    nodes: [{
      id: "start",
      type: "doc_reader",
      provider: "mock",
      model: "mock-deterministic",
      system_prompt: "",
      system_prompt_file: `workflows/${name}/nodes/start.md`,
      input_keys: [],
      output_keys: [],
      tools: [],
      retry_policy: { max_attempts: 1, backoff_seconds: 0 },
      human_approval: false,
      config: { ui: { x: 160, y: 160 } },
    }],
    edges: [],
  };
}

function subsystemConfig(node: WorkflowNode): BurrSubsystemConfig {
  return node.config as unknown as BurrSubsystemConfig;
}

function defaultTopology(workflowName = "workflow", nodeId = "burr_subsystem"): BurrTopology {
  return {
    entrypoint: "action_1",
    actions: [{
      id: "action_1",
      label: "First action",
      kind: "agent",
      reads: [],
      writes: [],
      prompt_file: `workflows/${workflowName}/subsystems/${nodeId}/actions/action_1.md`,
    }],
    transitions: [],
  };
}

function defaultBurrNode(id: string, workflowName: string): WorkflowNode {
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
            prompt_file: `workflows/${workflowName}/subsystems/${id}/actions/greet.md`,
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
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }));
}

function toFlowEdges(workflow: Workflow): Edge[] {
  return workflow.edges.map((edge, index) => ({
    ...flowEdgeOptions,
    id: `${edge.source}->${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.label || undefined,
  }));
}

function fromFlow(workflow: Workflow, nodes: Node[], edges: Edge[]): Workflow {
  const nodePositions = Object.fromEntries(nodes.map((node) => [node.id, node.position]));
  return {
    ...workflow,
    nodes: workflow.nodes.map((node) => {
      const {
        _resolved: _resolvedModel,
        resolved_system_prompt: _resolvedSystemPrompt,
        subsystem: _subsystem,
        subsystem_metadata: _subsystemMetadata,
        ...editableNode
      } = node;
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
  workflowName: string;
  nodeId: string;
  topology?: BurrTopology;
  onChange: (topology: BurrTopology) => void;
  openPrompt: (target: PromptTarget) => void;
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
        <button onClick={() => props.onChange(defaultTopology(props.workflowName, props.nodeId))}>Create Visualization Topology</button>
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
      actions: [...topology.actions, {
        id,
        label: "New action",
        kind: "agent",
        reads: [],
        writes: [],
        prompt_file: `workflows/${props.workflowName}/subsystems/${props.nodeId}/actions/${id}.md`,
      }],
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
          <div className="field">
            <span>Markdown prompt file</span>
            <div className="input-button-row">
              <input
                value={selectedAction.prompt_file ?? ""}
                onChange={(event) => updateAction(selectedAction.id, { prompt_file: event.target.value || null })}
                placeholder={`workflows/${props.workflowName}/subsystems/${props.nodeId}/actions/${selectedAction.id}.md`}
              />
              <button onClick={() => props.openPrompt({
                title: `Burr action metadata: ${props.nodeId}.${selectedAction.id}`,
                file: selectedAction.prompt_file ?? `workflows/${props.workflowName}/subsystems/${props.nodeId}/actions/${selectedAction.id}.md`,
                content: selectedAction.prompt ?? "",
                note: "Visualization metadata only. The Python Burr factory must load this file explicitly before it affects runtime behavior.",
                onSaved: (file, content) => updateAction(selectedAction.id, { prompt_file: file, prompt: content }),
              })}>Edit MD</button>
            </div>
          </div>
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

function CollapsibleSection(props: {
  title: string;
  badge?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(props.defaultOpen ?? false);
  return (
    <div className={`collapsible-section ${open ? "open" : ""}`}>
      <button className="collapsible-header" onClick={() => setOpen(!open)}>
        <span className="collapsible-arrow">{open ? "▼" : "▶"}</span>
        <strong>{props.title}</strong>
        {props.badge && <span className="collapsible-badge">{props.badge}</span>}
      </button>
      {open && <div className="collapsible-body">{props.children}</div>}
    </div>
  );
}

function NodeOutputViewer(props: {
  node: WorkflowNode;
  nodeOutputs: Record<string, unknown>;
  runId?: string;
  artifacts: Record<string, unknown>;
  metadata?: SubsystemRunMetadata;
  runtime?: NodeRuntimeState;
}) {
  const output = props.nodeOutputs[props.node.id];
  const hasOutput = output !== undefined && output !== null;
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

  return (
    <div className="node-output-viewer">
      <CollapsibleSection title="Node Output" badge={hasOutput ? "data" : undefined} defaultOpen={true}>
        {hasOutput
          ? <pre className="output-pre">{JSON.stringify(output, null, 2)}</pre>
          : <span className="subtle">No output recorded yet. Run the workflow to see results.</span>}
      </CollapsibleSection>

      {props.node.type === "burr_subsystem" && (
        <>
          <CollapsibleSection title="Runtime Artifacts" badge={artifactNames.length ? String(artifactNames.length) : undefined} defaultOpen={true}>
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
                : <span className="subtle">Run this workflow to inspect Burr state and trace artifacts.</span>}
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="Burr Action Sequence" badge={recentActionSequence.length ? String(recentActionSequence.length) : undefined} defaultOpen={recentActionSequence.length > 0}>
            <div className="action-sequence">
              {recentActionSequence.length
                ? recentActionSequence.map((action, index) => <code key={`${action}-${index}`}>{action}</code>)
                : <span className="subtle">No completed internal Burr actions recorded yet.</span>}
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="Burr Action Events" badge={recentActionEvents.length ? String(recentActionEvents.length) : undefined}>
            <div className="action-event-list">
              {recentActionEvents.length
                ? recentActionEvents.map((event) => (
                    <div key={event.id}>
                      <code>{eventAction(event) ?? "unknown action"}</code>
                      <span>{event.event_type.replace("burr_action_", "")}</span>
                    </div>
                  ))
                : <span className="subtle">No internal Burr actions recorded yet.</span>}
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="Subsystem Metadata" badge={props.metadata ? "ok" : undefined}>
            {props.metadata && <pre className="output-pre">{JSON.stringify(props.metadata, null, 2)}</pre>}
            {!props.metadata && <span className="subtle">Run this workflow to inspect subsystem metadata.</span>}
          </CollapsibleSection>
        </>
      )}
    </div>
  );
}

function SubsystemInspector(props: {
  node: WorkflowNode;
  workflowName: string;
  metadata?: SubsystemRunMetadata;
  artifacts: Record<string, unknown>;
  runId?: string;
  runtime?: NodeRuntimeState;
  openPrompt: (target: PromptTarget) => void;
  updateConfig: (patch: Partial<BurrSubsystemConfig>) => void;
  setStatus: (value: string) => void;
}) {
  const config = subsystemConfig(props.node);
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
      <TopologyEditor
        workflowName={props.workflowName}
        nodeId={props.node.id}
        topology={config.topology}
        onChange={(topology) => props.updateConfig({ topology })}
        openPrompt={props.openPrompt}
        setStatus={props.setStatus}
      />
    </div>
  );
}

function parseCurlBody(text: string): Record<string, unknown> | null {
  // Try to extract the -d/--data/--data-raw body from a curl command
  const dataMatch = text.match(/(?:-d\s+|--data(?:-raw)?\s+)'({[\s\S]*?})'/)
    ?? text.match(/(?:-d\s+|--data(?:-raw)?\s+)"({[\s\S]*?})"/)
    ?? text.match(/(?:-d\s+|--data(?:-raw)?\s+)({[\s\S]*?})(?:\s|$)/);
  if (!dataMatch) return null;
  try {
    return JSON.parse(dataMatch[1]);
  } catch {
    return null;
  }
}

function RunInputPanel(props: {
  workflow: Workflow;
  value: string;
  onChange: (value: string) => void;
}) {
  const entrypointNode = props.workflow.nodes.find((node) => node.id === props.workflow.entrypoint);
  const inputKeys = entrypointNode?.input_keys ?? [];

  const [mode, setMode] = useState<"structured" | "curl" | "raw">(
    inputKeys.length > 0 ? "structured" : "raw",
  );
  const [curlText, setCurlText] = useState("");
  const [structuredInputs, setStructuredInputs] = useState<Record<string, string>>(() => {
    const existing: Record<string, unknown> = (() => {
      try { return JSON.parse(props.value).inputs ?? {}; } catch { return {}; }
    })();
    return Object.fromEntries(inputKeys.map((key) => [key, typeof existing[key] === "string" ? existing[key] as string : ""]));
  });

  const syncFromStructured = (inputs: Record<string, string>) => {
    const cleaned = Object.fromEntries(Object.entries(inputs).filter(([, v]) => v !== ""));
    props.onChange(JSON.stringify({ inputs: cleaned }, null, 2));
  };

  const updateInput = (key: string, value: string) => {
    const next = { ...structuredInputs, [key]: value };
    setStructuredInputs(next);
    syncFromStructured(next);
  };

  const applyCurl = () => {
    const parsed = parseCurlBody(curlText);
    if (!parsed) {
      return;
    }
    const inputs = (parsed as { inputs?: Record<string, unknown> }).inputs ?? parsed;
    const filled = Object.fromEntries(inputKeys.map((key) => [key, typeof inputs[key] === "string" ? inputs[key] as string : JSON.stringify(inputs[key])]));
    setStructuredInputs(filled);
    syncFromStructured(filled);
    setMode("structured");
  };

  return (
    <div className="run-input-panel">
      <div className="section-heading">
        <h2>Run Inputs</h2>
        <div className="mode-tabs">
          {inputKeys.length > 0 && (
            <button className={mode === "structured" ? "active" : ""} onClick={() => setMode("structured")}>Fields</button>
          )}
          <button className={mode === "curl" ? "active" : ""} onClick={() => setMode("curl")}>Paste curl</button>
          <button className={mode === "raw" ? "active" : ""} onClick={() => setMode("raw")}>Raw JSON</button>
        </div>
      </div>
      {mode === "structured" && inputKeys.length > 0 && (
        <div className="structured-inputs">
          {inputKeys.map((key) => (
            <label className="field" key={key}>
              <span>{key}</span>
              <textarea
                value={structuredInputs[key] ?? ""}
                onChange={(event) => updateInput(key, event.target.value)}
                rows={3}
                placeholder={`Value for ${key}`}
              />
            </label>
          ))}
        </div>
      )}
      {mode === "curl" && (
        <div className="curl-input">
          <label className="field">
            <span>Paste a curl command</span>
            <textarea
              value={curlText}
              onChange={(event) => setCurlText(event.target.value)}
              rows={5}
              placeholder={`curl -X POST http://localhost:8000/workflows/my_workflow/run \\\n  -H 'Content-Type: application/json' \\\n  -d '{"inputs":{"key":"value"}}'`}
            />
          </label>
          <button className="primary" onClick={applyCurl}>Parse &amp; Fill</button>
        </div>
      )}
      {mode === "raw" && (
        <label className="field">
          <span>Request body JSON</span>
          <textarea
            className="raw-input"
            value={props.value}
            onChange={(event) => props.onChange(event.target.value)}
            rows={6}
          />
        </label>
      )}
    </div>
  );
}

function PanelResizer(props: {
  side: PanelSide;
  width: number;
  startResize: (side: PanelSide, event: React.PointerEvent<HTMLDivElement>) => void;
  nudge: (side: PanelSide, delta: number) => void;
  reset: (side: PanelSide) => void;
}) {
  const label = props.side === "left" ? "Resize workflow panel" : "Resize inspector panel";
  return (
    <div
      className={`panel-resizer panel-resizer-${props.side}`}
      role="separator"
      aria-label={label}
      aria-orientation="vertical"
      aria-valuenow={props.width}
      tabIndex={0}
      title={`${label}. Drag or use arrow keys. Double-click to reset.`}
      onPointerDown={(event) => props.startResize(props.side, event)}
      onDoubleClick={() => props.reset(props.side)}
      onKeyDown={(event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        props.nudge(props.side, event.key === "ArrowRight" ? 24 : -24);
      }}
    >
      <span className="panel-resizer-grip" />
    </div>
  );
}

function App() {
  const [workflowNames, setWorkflowNames] = useState<string[]>([]);
  const [catalog, setCatalog] = useState<Catalog>(emptyCatalog);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [status, setStatus] = useState("Loading...");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [runRecord, setRunRecord] = useState<RunRecord | null>(null);
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [promptTarget, setPromptTarget] = useState<PromptTarget | null>(null);
  const [runInput, setRunInput] = useState('{\n  "inputs": {}\n}');
  const [theme, setTheme] = useState<ColorTheme>(storedTheme);
  const [panelWidths, setPanelWidths] = useState(storedPanelWidths);
  const runtimeByNode = useMemo(() => deriveRuntimeByNode(workflow, runEvents), [workflow, runEvents]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(themeStorageKey, theme);
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem(panelWidthStorageKey, JSON.stringify(panelWidths));
  }, [panelWidths]);

  useEffect(() => {
    const fitPanelsToWindow = () => setPanelWidths((current) => fitPanelWidths(current, window.innerWidth));
    window.addEventListener("resize", fitPanelsToWindow);
    return () => window.removeEventListener("resize", fitPanelsToWindow);
  }, []);

  const startPanelResize = useCallback((side: PanelSide, event: React.PointerEvent<HTMLDivElement>) => {
    if (window.matchMedia("(max-width: 1060px)").matches) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidths = panelWidths;
    const shellWidth = event.currentTarget.parentElement?.getBoundingClientRect().width ?? window.innerWidth;
    document.body.classList.add("panel-resizing");

    const resize = (pointerEvent: PointerEvent) => {
      const delta = pointerEvent.clientX - startX;
      setPanelWidths(fitPanelWidths({
        ...startWidths,
        [side]: side === "left" ? startWidths.left + delta : startWidths.right - delta,
      }, shellWidth));
    };
    const stopResize = () => {
      document.body.classList.remove("panel-resizing");
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
    };

    window.addEventListener("pointermove", resize);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  }, [panelWidths]);

  const nudgePanel = (side: PanelSide, delta: number) => {
    setPanelWidths((current) => fitPanelWidths({
      ...current,
      [side]: side === "left" ? current.left + delta : current.right - delta,
    }, window.innerWidth));
  };

  const resetPanel = (side: PanelSide) => {
    setPanelWidths((current) => fitPanelWidths({ ...current, [side]: defaultPanelWidths[side] }, window.innerWidth));
  };

  const loadWorkflow = useCallback(async (name: string) => {
    try {
      const loaded = await api<Workflow>(`/workflows/${name}`);
      setWorkflow(loaded);
      setNodes(toFlowNodes(loaded));
      setEdges(toFlowEdges(loaded));
      setSelectedNodeId(loaded.nodes[0]?.id ?? null);
      setRunRecord(null);
      setRunEvents([]);
      setRunInput('{\n  "inputs": {}\n}');
      setStatus(`Loaded ${name}`);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }, []);

  const refreshWorkflowNames = useCallback(async () => {
    const data = await api<{ workflows: string[] }>("/workflows");
    setWorkflowNames(data.workflows);
    return data.workflows;
  }, []);

  useEffect(() => {
    Promise.all([refreshWorkflowNames(), api<Catalog>("/catalog")])
      .then(async ([names, loadedCatalog]) => {
        setCatalog(loadedCatalog);
        const initial = names.includes("starter_three_node") ? "starter_three_node" : names[0];
        if (initial) await loadWorkflow(initial);
      })
      .catch((error) => setStatus(error.message));
  }, [loadWorkflow, refreshWorkflowNames]);

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

  const patchSelectedNode = (patch: Partial<WorkflowNode>) => {
    updateSelectedNode((node) => ({ ...node, ...patch }));
  };

  const renameSelectedNode = (requestedId: string) => {
    if (!currentWorkflow || !selectedNodeId) return;
    const nextId = slugify(requestedId);
    if (nextId !== selectedNodeId && currentWorkflow.nodes.some((node) => node.id === nextId)) {
      setStatus(`Node id already exists: ${nextId}`);
      return;
    }
    if (nextId === selectedNodeId) return;
    replaceWorkflow({
      ...currentWorkflow,
      entrypoint: currentWorkflow.entrypoint === selectedNodeId ? nextId : currentWorkflow.entrypoint,
      nodes: currentWorkflow.nodes.map((node) => node.id === selectedNodeId ? { ...node, id: nextId } : node),
      edges: currentWorkflow.edges.map((edge) => ({
        ...edge,
        source: edge.source === selectedNodeId ? nextId : edge.source,
        target: edge.target === selectedNodeId ? nextId : edge.target,
      })),
    }, nextId);
  };

  const changeSelectedNodeType = (nodeType: string) => {
    if (!selectedNode || !workflow || nodeType === selectedNode.type) return;
    if (nodeType === "burr_subsystem") {
      const burrNode = defaultBurrNode(selectedNode.id, workflow.name);
      patchSelectedNode({ type: nodeType, config: { ...burrNode.config, ui: selectedNode.config.ui } });
      return;
    }
    patchSelectedNode({ type: nodeType, config: { ui: selectedNode.config.ui } });
  };

  const updateSubsystemConfig = (patch: Partial<BurrSubsystemConfig>) => {
    updateSelectedNode((node) => ({ ...node, config: { ...node.config, ...patch } }));
  };

  const validate = async () => {
    if (!currentWorkflow) return;
    await api("/workflows/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentWorkflow),
    });
  };

  const openPrompt = async (target: PromptTarget) => {
    try {
      const prompt = await api<{ content: string }>(`/prompts/${promptPath(target.file)}`);
      setPromptTarget({ ...target, content: prompt.content });
    } catch {
      setPromptTarget(target);
    }
  };

  const save = async () => {
    if (!currentWorkflow) return;
    try {
      await validate();
      await api(`/workflows/${currentWorkflow.name}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentWorkflow),
      });
      await refreshWorkflowNames();
      setStatus(`Saved ${currentWorkflow.name}`);
    } catch (error) {
      setStatus(`Save failed: ${(error as Error).message}`);
    }
  };

  const run = async () => {
    if (!currentWorkflow) return;
    try {
      await validate();
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
    (connection: Connection) => setEdges((current) => addEdge({ ...flowEdgeOptions, ...connection }, current)),
    [],
  );

  const addNode = (type: string) => {
    if (!currentWorkflow) return;
    const id = uniqueId(type, currentWorkflow.nodes.map((node) => node.id));
    const newNode: WorkflowNode = type === "burr_subsystem"
      ? defaultBurrNode(id, currentWorkflow.name)
      : {
          id,
          type,
          provider: "mock",
          model: "mock-deterministic",
          system_prompt: "",
          system_prompt_file: `workflows/${currentWorkflow.name}/nodes/${id}.md`,
          input_keys: [],
          output_keys: [],
          tools: [],
          retry_policy: { max_attempts: 1, backoff_seconds: 0 },
          human_approval: false,
          config: { ui: { x: 160, y: 160 } },
        };
    replaceWorkflow({ ...currentWorkflow, nodes: [...currentWorkflow.nodes, newNode] }, id);
  };

  const newDraft = () => {
    replaceWorkflow(draftWorkflow(), "start");
    setRunRecord(null);
    setRunEvents([]);
    setStatus("Created draft workflow. Save to persist YAML.");
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
    <>
    <main
      className="app-shell"
      style={{
        "--left-panel-width": `${panelWidths.left}px`,
        "--right-panel-width": `${panelWidths.right}px`,
      } as React.CSSProperties}
    >
      <header className="app-topbar">
        <div className="brand-mark" aria-hidden="true">WF</div>
        <div className="app-brand">
          <span className="eyebrow">Workflow Studio</span>
          <div className="app-title-row">
            <h1>Agentic Editor</h1>
            {workflow && <span className="workspace-pill">{workflow.nodes.length} node{workflow.nodes.length === 1 ? "" : "s"}</span>}
          </div>
        </div>
        <p className="topbar-status" role="status">
          <span className="status-dot" />
          <span>{status}</span>
        </p>
        <div className="topbar-actions">
          <button
            className="theme-toggle"
            aria-pressed={theme === "light"}
            onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? "Light Mode" : "Dark Mode"}
          </button>
          <button className="primary" onClick={save}>Save Workflow</button>
          <button className="run-button" onClick={run}>Run Workflow</button>
          <button onClick={() => validate().then(() => setStatus("Workflow is valid")).catch((error) => setStatus(`Validation failed: ${error.message}`))}>Validate</button>
          <button onClick={newDraft}>New Draft</button>
        </div>
      </header>
      <aside className="left-panel">
        <section className="sidebar-section workflow-picker">
          <div className="sidebar-heading">
            <div>
              <span className="eyebrow">Workspace</span>
              <h2>Workflow Library</h2>
            </div>
            <span className="count-badge">{workflowNames.length}</span>
          </div>
          <label className="field">
            <span>Active workflow</span>
            <select value={workflow?.name ?? ""} onChange={(event) => loadWorkflow(event.target.value)}>
              {workflowNames.map((name) => <option key={name}>{name}</option>)}
            </select>
          </label>
        </section>
        {workflow && (
          <CollapsibleSection title="Workflow Details">
            <WorkflowSettings workflow={workflow} update={(patch) => setWorkflow((current) => current ? { ...current, ...patch } : current)} />
          </CollapsibleSection>
        )}
        <section className="sidebar-section palette">
          <div className="sidebar-heading">
            <div>
              <span className="eyebrow">Build</span>
              <h2>Add Nodes</h2>
            </div>
            <span className="count-badge">{catalog.node_types.length}</span>
          </div>
          <p className="section-description">Add a node, then connect it on the canvas.</p>
          <div className="palette-list">
            {catalog.node_types.map((nodeType) => (
              <button className={nodeType === "burr_subsystem" ? "subsystem-add" : ""} key={nodeType} onClick={() => addNode(nodeType)}>
                <strong>{nodeType === "burr_subsystem" ? "SUB" : "+"}</strong><span>{nodeType}</span>
              </button>
            ))}
          </div>
        </section>
        <section className="sidebar-section node-list">
          <div className="sidebar-heading">
            <div>
              <span className="eyebrow">Navigate</span>
              <h2>Workflow Nodes</h2>
            </div>
            <span className="count-badge">{workflow?.nodes.length ?? 0}</span>
          </div>
          <div className="node-list-items">
            {workflow?.nodes.map((node) => (
              <button className={node.id === selectedNodeId ? "selected" : ""} key={node.id} onClick={() => setSelectedNodeId(node.id)}>
                <span>{node.type === "burr_subsystem" ? "SUB" : "NODE"}</span>
                <strong>{node.id}</strong>
                <small>{node.type}</small>
              </button>
            ))}
          </div>
        </section>
        {workflow && (
          <CollapsibleSection title="Run Workflow" defaultOpen={true}>
            <RunInputPanel
              key={workflow.name}
              workflow={workflow}
              value={runInput}
              onChange={setRunInput}
            />
          </CollapsibleSection>
        )}
        {runRecord && (
          <div className="run-summary">
            <div className="section-heading">
              <h2>Latest Run</h2>
              <span className={`runtime-chip runtime-chip-${runRecord.status}`}>{runRecord.status}</span>
            </div>
            <code>{runRecord.run_id}</code>
            {runRecord.error && <pre>{runRecord.error}</pre>}
          </div>
        )}
        <CollapsibleSection title="Run History" badge={runEvents.length ? String(runEvents.length) : undefined}>
          <RuntimeTimeline events={runEvents} runId={runRecord?.run_id} />
        </CollapsibleSection>
        {currentWorkflow && (
          <CollapsibleSection title="Connections" badge={currentWorkflow.edges.length ? String(currentWorkflow.edges.length) : undefined}>
            <EdgeEditor workflow={currentWorkflow} update={(nextWorkflow) => replaceWorkflow(nextWorkflow, selectedNodeId)} />
          </CollapsibleSection>
        )}
        {currentWorkflow && (
          <CollapsibleSection title="Advanced JSON">
            <WorkflowJsonEditor workflow={currentWorkflow} load={(nextWorkflow) => replaceWorkflow(nextWorkflow, nextWorkflow.nodes[0]?.id ?? null)} setStatus={setStatus} />
          </CollapsibleSection>
        )}
      </aside>
      <PanelResizer
        side="left"
        width={panelWidths.left}
        startResize={startPanelResize}
        nudge={nudgePanel}
        reset={resetPanel}
      />
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
          connectionLineStyle={{ stroke: flowEdgeColor, strokeWidth: 2 }}
          connectionLineType={ConnectionLineType.SmoothStep}
          elevateEdgesOnSelect
          fitView
        >
          <Background color={theme === "light" ? "#cbd5e1" : "#26364d"} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </section>
      <PanelResizer
        side="right"
        width={panelWidths.right}
        startResize={startPanelResize}
        nudge={nudgePanel}
        reset={resetPanel}
      />
      <aside className="right-panel">
        <div className="inspector-heading">
          <div>
            <span className="eyebrow">Inspector</span>
            <h2>{selectedNode?.id ?? "Select a node"}</h2>
          </div>
          {selectedNode && <span className="node-type-badge">{selectedNode.type}</span>}
        </div>
        {!selectedNode && <p>Select a node to edit its configuration.</p>}
        {selectedNode && workflow && (
          <CommonNodeInspector
            node={selectedNode}
            workflowName={workflow.name}
            catalog={catalog}
            runtimeStatus={visibleNodeStatus(selectedNode, selectedNodeRuntime)}
            updateNode={patchSelectedNode}
            changeNodeType={changeSelectedNodeType}
            renameNode={renameSelectedNode}
            openPrompt={(target) => void openPrompt(target)}
            setStatus={setStatus}
          />
        )}
        {selectedNode?.type === "burr_subsystem" && (
          <SubsystemInspector
            node={selectedNode}
            workflowName={workflow?.name ?? "workflow"}
            metadata={subsystemMetadata}
            artifacts={subsystemArtifacts}
            runId={runRecord?.run_id}
            runtime={selectedNodeRuntime}
            openPrompt={(target) => void openPrompt(target)}
            updateConfig={updateSubsystemConfig}
            setStatus={setStatus}
          />
        )}
        {selectedNode && (
          <NodeOutputViewer
            node={selectedNode}
            nodeOutputs={runRecord?.state?.node_outputs ?? {}}
            runId={runRecord?.run_id}
            artifacts={subsystemArtifacts}
            metadata={subsystemMetadata}
            runtime={selectedNodeRuntime}
          />
        )}
        {selectedNode && workflow && workflow.nodes.length > 1 && (
          <button className="danger delete-node" onClick={deleteSelectedNode}>Delete Selected Node</button>
        )}
      </aside>
    </main>
    {promptTarget && (
      <MarkdownEditor
        target={promptTarget}
        savePrompt={savePrompt}
        close={() => setPromptTarget(null)}
        setStatus={setStatus}
      />
    )}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ReactFlowProvider>
      <App />
    </ReactFlowProvider>
  </React.StrictMode>,
);
