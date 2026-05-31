export type BurrAction = {
  id: string;
  label?: string;
  kind?: "agent" | "action" | "router" | "tool" | "human";
  description?: string;
  reads?: string[];
  writes?: string[];
  model?: string | null;
  prompt?: string;
  prompt_file?: string | null;
};

export type BurrTransition = {
  source: string;
  target: string;
  condition?: string;
};

export type BurrTopology = {
  entrypoint: string;
  actions: BurrAction[];
  transitions: BurrTransition[];
};

export type BurrSubsystemConfig = {
  app_module: string;
  app_factory: string;
  input_map: Record<string, string>;
  output_map: Record<string, string>;
  halt_after?: string[];
  terminal_states?: string[];
  artifact_name?: string;
  timeout_seconds?: number;
  fail_on_error?: boolean;
  topology?: BurrTopology;
  ui?: { x?: number; y?: number };
};

export type WorkflowNode = {
  id: string;
  type: string;
  provider?: string | null;
  model?: string | null;
  system_prompt?: string;
  system_prompt_file?: string | null;
  resolved_system_prompt?: string;
  input_keys: string[];
  output_keys: string[];
  tools: string[];
  mcps?: string[];
  retry_policy: { max_attempts: number; backoff_seconds: number };
  human_approval: boolean;
  config: Record<string, unknown> & { ui?: { x?: number; y?: number } };
  subsystem?: boolean;
  subsystem_metadata?: {
    runtime: string;
    app_module: string;
    app_factory: string;
    has_internal_trace: boolean;
    artifact_names: string[];
    topology?: BurrTopology;
  };
};

export type WorkflowEdge = {
  source: string;
  target: string;
  label?: string | null;
};

export type Workflow = {
  name: string;
  version: string;
  description: string;
  entrypoint: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
};

export type SubsystemRunMetadata = {
  node_id: string;
  runtime: string;
  app_module: string;
  app_factory: string;
  status: string;
  terminal_state?: string | null;
  halt_reason?: string | null;
  duration_ms?: number | null;
  input_map?: Record<string, string>;
  output_map?: Record<string, string>;
  has_internal_trace?: boolean;
  artifact_names?: string[];
};

export type WorkflowState = {
  artifacts: Record<string, Record<string, unknown>>;
  _subsystems?: Record<string, SubsystemRunMetadata>;
  logs: string[];
  node_outputs: Record<string, unknown>;
  final_report?: string | null;
};

export type RunRecord = {
  run_id: string;
  workflow_name: string;
  status: string;
  state?: WorkflowState | null;
  error?: string | null;
};

export type RunEvent = {
  id: number;
  run_id: string;
  timestamp: string;
  event_type: string;
  node_id?: string | null;
  payload: Record<string, unknown>;
};

export type Catalog = {
  providers: { id: string; type: string; default_model: string }[];
  tools: { id: string; type: string; enabled: boolean }[];
  mcps: { id: string; name: string; transport: string; enabled: boolean }[];
  node_types: string[];
};
