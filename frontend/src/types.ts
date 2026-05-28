export type WorkflowNode = {
  id: string;
  type: string;
  provider?: string | null;
  model?: string | null;
  system_prompt?: string;
  input_keys: string[];
  output_keys: string[];
  tools: string[];
  mcps?: string[];
  retry_policy: { max_attempts: number; backoff_seconds: number };
  human_approval: boolean;
  config: Record<string, unknown> & { ui?: { x?: number; y?: number } };
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
