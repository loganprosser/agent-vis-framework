import React, { useEffect, useState } from "react";
import type { Catalog, Workflow, WorkflowNode } from "./types";

const csv = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
const csvValue = (value?: string[]) => (value ?? []).join(", ");

export type PromptTarget = {
  title: string;
  file: string;
  content: string;
  note?: string;
  onSaved: (file: string, content: string) => void;
};

export function MarkdownEditor(props: {
  target: PromptTarget;
  savePrompt: (file: string, content: string) => Promise<void>;
  close: () => void;
  setStatus: (status: string) => void;
}) {
  const [file, setFile] = useState(props.target.file);
  const [content, setContent] = useState(props.target.content);

  const save = async () => {
    try {
      await props.savePrompt(file, content);
      props.target.onSaved(file, content);
      props.setStatus(`Saved Markdown prompt: ${file}`);
    } catch (error) {
      props.setStatus(`Prompt save failed: ${(error as Error).message}`);
    }
  };

  return (
    <div className="md-overlay">
      <header className="md-topbar">
        <div>
          <strong>{props.target.title}</strong>
          <p>{props.target.note ?? "Markdown file under configs/prompts/. This file is the editable source of truth."}</p>
        </div>
        <div className="button-row compact-buttons">
          <button className="primary" onClick={save}>Save MD</button>
          <button onClick={props.close}>Back</button>
        </div>
      </header>
      <label className="field md-path">
        <span>Prompt file beneath configs/prompts/</span>
        <input value={file} onChange={(event) => setFile(event.target.value)} />
      </label>
      <div className="md-split">
        <label className="field">
          <span>Markdown</span>
          <textarea value={content} onChange={(event) => setContent(event.target.value)} spellCheck={false} />
        </label>
        <div className="field">
          <span>Preview</span>
          <pre className="md-preview">{content || "Nothing written yet."}</pre>
        </div>
      </div>
    </div>
  );
}

function JsonObjectEditor(props: {
  label: string;
  value: Record<string, unknown>;
  update: (value: Record<string, unknown>) => void;
  setStatus: (status: string) => void;
}) {
  const [text, setText] = useState(JSON.stringify(props.value, null, 2));
  useEffect(() => setText(JSON.stringify(props.value, null, 2)), [props.value]);

  const apply = () => {
    try {
      const parsed = JSON.parse(text) as unknown;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("must be a JSON object");
      props.update(parsed as Record<string, unknown>);
      props.setStatus(`${props.label} updated. Save to persist.`);
    } catch (error) {
      props.setStatus(`${props.label}: ${(error as Error).message}`);
    }
  };

  return (
    <label className="field">
      <span>{props.label}</span>
      <textarea value={text} onChange={(event) => setText(event.target.value)} onBlur={apply} rows={7} />
    </label>
  );
}

function ChoiceChips(props: {
  label: string;
  choices: { id: string; detail: string }[];
  selected: string[];
  update: (selected: string[]) => void;
}) {
  return (
    <div className="field">
      <span>{props.label}</span>
      <div className="choice-list">
        {props.choices.map((choice) => (
          <label className="choice-chip" key={choice.id}>
            <input
              type="checkbox"
              checked={props.selected.includes(choice.id)}
              onChange={(event) => props.update(event.target.checked
                ? [...props.selected, choice.id]
                : props.selected.filter((id) => id !== choice.id))}
            />
            <span>{choice.id}</span>
            <small>{choice.detail}</small>
          </label>
        ))}
        {props.choices.length === 0 && <em className="subtle">None configured.</em>}
      </div>
    </div>
  );
}

export function CommonNodeInspector(props: {
  node: WorkflowNode;
  workflowName: string;
  catalog: Catalog;
  runtimeStatus: string;
  updateNode: (patch: Partial<WorkflowNode>) => void;
  changeNodeType: (nodeType: string) => void;
  renameNode: (id: string) => void;
  openPrompt: (target: PromptTarget) => void;
  setStatus: (status: string) => void;
}) {
  const provider = props.catalog.providers.find((item) => item.id === props.node.provider);
  const promptFile = props.node.system_prompt_file
    ?? `workflows/${props.workflowName}/nodes/${props.node.id}.md`;
  const regularTools = props.catalog.tools.filter((tool) => tool.type !== "mcp");
  const mcpTools = props.catalog.tools.filter((tool) => tool.type === "mcp");

  return (
    <div className="inspector-content common-node-editor">
      <div className="section-heading">
        <h3>Node Contract</h3>
        <span className={`runtime-chip runtime-chip-${props.runtimeStatus}`}>{props.runtimeStatus}</span>
      </div>
      <div className="two-column">
        <label className="field">
          <span>Node ID</span>
          <input value={props.node.id} onChange={(event) => props.renameNode(event.target.value)} />
        </label>
        <label className="field">
          <span>Node type</span>
          <select value={props.node.type} onChange={(event) => props.changeNodeType(event.target.value)}>
            {props.catalog.node_types.map((nodeType) => <option key={nodeType}>{nodeType}</option>)}
          </select>
        </label>
      </div>
      <div className="two-column">
        <label className="field">
          <span>Provider</span>
          <select
            value={props.node.provider ?? ""}
            onChange={(event) => {
              const nextProvider = props.catalog.providers.find((item) => item.id === event.target.value);
              props.updateNode({ provider: event.target.value || null, model: nextProvider?.default_model ?? null });
            }}
          >
            <option value="">default</option>
            {props.catalog.providers.map((item) => <option key={item.id} value={item.id}>{item.id} ({item.type})</option>)}
          </select>
        </label>
        <label className="field">
          <span>Model</span>
          <input
            value={props.node.model ?? provider?.default_model ?? ""}
            onChange={(event) => props.updateNode({ model: event.target.value || null })}
          />
        </label>
      </div>
      <label className="field">
        <span>System prompt fallback</span>
        <textarea
          value={props.node.resolved_system_prompt ?? props.node.system_prompt ?? ""}
          onChange={(event) => props.updateNode({ system_prompt: event.target.value, resolved_system_prompt: event.target.value })}
          rows={4}
        />
      </label>
      <div className="field">
        <span>Markdown prompt file</span>
        <div className="input-button-row">
          <input value={props.node.system_prompt_file ?? ""} onChange={(event) => props.updateNode({ system_prompt_file: event.target.value || null })} placeholder={promptFile} />
          <button onClick={() => props.openPrompt({
            title: `Node prompt: ${props.node.id}`,
            file: promptFile,
            content: props.node.resolved_system_prompt ?? props.node.system_prompt ?? "",
            onSaved: (file, content) => props.updateNode({ system_prompt_file: file, system_prompt: content, resolved_system_prompt: content }),
          })}>Edit MD</button>
        </div>
      </div>
      <div className="two-column">
        <label className="field">
          <span>Input keys</span>
          <input value={csvValue(props.node.input_keys)} onChange={(event) => props.updateNode({ input_keys: csv(event.target.value) })} />
        </label>
        <label className="field">
          <span>Output keys</span>
          <input value={csvValue(props.node.output_keys)} onChange={(event) => props.updateNode({ output_keys: csv(event.target.value) })} />
        </label>
      </div>
      <ChoiceChips
        label="Tools"
        choices={regularTools.map((tool) => ({ id: tool.id, detail: `${tool.type}${tool.enabled ? "" : " disabled"}` }))}
        selected={props.node.tools.filter((id) => !mcpTools.some((tool) => tool.id === id))}
        update={(tools) => props.updateNode({ tools: [...tools, ...props.node.tools.filter((id) => mcpTools.some((tool) => tool.id === id))] })}
      />
      <ChoiceChips
        label="MCP-backed tools"
        choices={mcpTools.map((tool) => ({ id: tool.id, detail: tool.enabled ? "mcp" : "mcp disabled" }))}
        selected={props.node.tools.filter((id) => mcpTools.some((tool) => tool.id === id))}
        update={(mcpTools) => props.updateNode({ tools: [...props.node.tools.filter((id) => !props.catalog.tools.some((tool) => tool.type === "mcp" && tool.id === id)), ...mcpTools] })}
      />
      <div className="two-column">
        <label className="field">
          <span>Retry attempts</span>
          <input type="number" min="1" value={props.node.retry_policy.max_attempts} onChange={(event) => props.updateNode({ retry_policy: { ...props.node.retry_policy, max_attempts: Number(event.target.value) } })} />
        </label>
        <label className="field">
          <span>Backoff seconds</span>
          <input type="number" min="0" step=".1" value={props.node.retry_policy.backoff_seconds} onChange={(event) => props.updateNode({ retry_policy: { ...props.node.retry_policy, backoff_seconds: Number(event.target.value) } })} />
        </label>
      </div>
      <label className="check-field">
        <input type="checkbox" checked={props.node.human_approval} onChange={(event) => props.updateNode({ human_approval: event.target.checked })} />
        <span>Human approval required</span>
      </label>
      {props.node.type !== "burr_subsystem" && (
        <JsonObjectEditor label="Node config JSON" value={props.node.config} update={(config) => props.updateNode({ config })} setStatus={props.setStatus} />
      )}
    </div>
  );
}

export function WorkflowSettings(props: {
  workflow: Workflow;
  update: (patch: Partial<Workflow>) => void;
}) {
  return (
    <div className="workflow-settings">
      <h2>Workflow Contract</h2>
      <label className="field">
        <span>Name</span>
        <input value={props.workflow.name} onChange={(event) => props.update({ name: event.target.value })} />
      </label>
      <div className="two-column">
        <label className="field">
          <span>Version</span>
          <input value={props.workflow.version} onChange={(event) => props.update({ version: event.target.value })} />
        </label>
        <label className="field">
          <span>Entrypoint</span>
          <select value={props.workflow.entrypoint} onChange={(event) => props.update({ entrypoint: event.target.value })}>
            {props.workflow.nodes.map((node) => <option key={node.id}>{node.id}</option>)}
          </select>
        </label>
      </div>
      <label className="field">
        <span>Description</span>
        <textarea value={props.workflow.description} onChange={(event) => props.update({ description: event.target.value })} rows={3} />
      </label>
    </div>
  );
}

export function EdgeEditor(props: {
  workflow: Workflow;
  update: (workflow: Workflow) => void;
}) {
  return (
    <div className="workflow-settings">
      <h2>Edges</h2>
      {props.workflow.edges.map((edge, index) => (
        <div className="edge-editor" key={`${edge.source}-${edge.target}-${index}`}>
          <strong>{edge.source} → {edge.target}</strong>
          <input
            value={edge.label ?? ""}
            onChange={(event) => props.update({
              ...props.workflow,
              edges: props.workflow.edges.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item),
            })}
            placeholder="Visual label"
          />
          <button
            className="danger icon-button"
            onClick={() => props.update({ ...props.workflow, edges: props.workflow.edges.filter((_item, itemIndex) => itemIndex !== index) })}
          >×</button>
        </div>
      ))}
      {props.workflow.edges.length === 0 && <span className="subtle">No edges yet. Connect handles on the canvas.</span>}
    </div>
  );
}

export function WorkflowJsonEditor(props: {
  workflow: Workflow;
  load: (workflow: Workflow) => void;
  setStatus: (status: string) => void;
}) {
  const [text, setText] = useState(JSON.stringify(props.workflow, null, 2));
  useEffect(() => setText(JSON.stringify(props.workflow, null, 2)), [props.workflow]);

  const load = () => {
    try {
      props.load(JSON.parse(text) as Workflow);
      props.setStatus("Loaded workflow JSON. Save to persist YAML.");
    } catch (error) {
      props.setStatus(`Invalid workflow JSON: ${(error as Error).message}`);
    }
  };

  return (
    <div className="workflow-settings">
      <div className="section-heading">
        <h2>Workflow JSON</h2>
        <button onClick={load}>Load JSON</button>
      </div>
      <textarea value={text} onChange={(event) => setText(event.target.value)} rows={10} spellCheck={false} />
    </div>
  );
}
