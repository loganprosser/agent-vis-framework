from __future__ import annotations

from fastapi.responses import HTMLResponse


INDEX_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Agentic Workflow Editor</title>
    <script>
      (() => {
        const savedTheme = localStorage.getItem("agenticWorkflowTheme");
        const systemTheme = window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
        document.documentElement.dataset.theme = savedTheme || systemTheme || "dark";
      })();
    </script>
    <style>
      :root {
        color-scheme: dark;
        --bg: #0f131a;
        --panel: #171c25;
        --panel-2: #202633;
        --field: #111722;
        --ink: #eef2f7;
        --muted: #9aa6b7;
        --line: #2c3442;
        --line-strong: #485366;
        --topbar: rgba(23, 28, 37, .88);
        --canvas: #10151e;
        --grid-line: rgba(154, 166, 183, .12);
        --accent: #2dd4bf;
        --accent-dark: #0f766e;
        --accent-soft: rgba(45, 212, 191, .16);
        --amber: #f59e0b;
        --violet: #a78bfa;
        --danger: #f97066;
        --edge: #94a3b8;
        --edge-label-bg: #1f2937;
        --edge-label-ink: #f8fafc;
        --shadow: 0 18px 38px rgba(0, 0, 0, .30);
        --node-w: 264px;
        --node-h: 122px;
      }
      :root[data-theme="light"] {
        color-scheme: light;
        --bg: #f4f5f7;
        --panel: #ffffff;
        --panel-2: #fbfcfe;
        --field: #ffffff;
        --ink: #17202c;
        --muted: #697586;
        --line: #d7dde7;
        --line-strong: #aab4c3;
        --topbar: rgba(255, 255, 255, .86);
        --canvas: #f7f8fb;
        --grid-line: rgba(107, 114, 128, .11);
        --accent: #0f766e;
        --accent-dark: #0d5f59;
        --accent-soft: #d9f2ee;
        --amber: #b45309;
        --violet: #6d5bd0;
        --danger: #b42318;
        --edge: #8c98aa;
        --edge-label-bg: #ffffff;
        --edge-label-ink: #344054;
        --shadow: 0 14px 30px rgba(16, 24, 40, .10);
      }
      * { box-sizing: border-box; }
      html, body { height: 100%; }
      body {
        margin: 0;
        overflow: hidden;
        background: var(--bg);
        color: var(--ink);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      button, input, textarea, select { font: inherit; }
      button {
        min-height: 34px;
        border-radius: 7px;
        cursor: pointer;
        padding: 7px 10px;
      }
      input, textarea, select {
        width: 100%;
        border: 1px solid var(--line);
        border-radius: 7px;
        background: var(--field);
        color: var(--ink);
        padding: 8px 9px;
      }
      textarea {
        min-height: 86px;
        resize: vertical;
        line-height: 1.42;
      }
      label {
        color: var(--muted);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: .04em;
        text-transform: uppercase;
      }
      .app {
        display: grid;
        grid-template-columns: 270px minmax(520px, 1fr) 410px;
        height: 100vh;
      }
      .left, .right {
        min-width: 0;
        background: var(--panel);
        border-color: var(--line);
        border-style: solid;
        overflow: auto;
      }
      .left {
        border-width: 0 1px 0 0;
        padding: 16px;
      }
      .right {
        border-width: 0 0 0 1px;
        padding: 16px;
      }
      .workspace {
        min-width: 0;
        display: grid;
        grid-template-rows: auto minmax(0, 1fr);
      }
      .topbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        min-height: 64px;
        padding: 12px 16px;
        background: var(--topbar);
        border-bottom: 1px solid var(--line);
        backdrop-filter: blur(10px);
      }
      .title h1 {
        margin: 0 0 2px;
        font-size: 18px;
        line-height: 1.2;
      }
      .subtle {
        color: var(--muted);
        font-size: 12px;
        line-height: 1.45;
      }
      .brand {
        margin: 0 0 4px;
        font-size: 17px;
        font-weight: 850;
      }
      .section {
        margin-top: 18px;
      }
      .section-title {
        margin: 0 0 8px;
        color: var(--muted);
        font-size: 11px;
        font-weight: 850;
        letter-spacing: .05em;
        text-transform: uppercase;
      }
      .stack { display: grid; gap: 8px; }
      .row { display: flex; gap: 8px; align-items: center; }
      .row > * { min-width: 0; }
      .primary {
        border: 1px solid #0d5f59;
        background: var(--accent);
        color: #fff;
        font-weight: 800;
      }
      .secondary {
        border: 1px solid var(--line);
        background: var(--field);
        color: var(--ink);
      }
      .danger {
        border: 1px solid #f1b8b2;
        background: var(--field);
        color: var(--danger);
      }
      .workflow-button {
        width: 100%;
        border: 1px solid var(--line);
        background: var(--field);
        color: var(--ink);
        text-align: left;
      }
      .workflow-button.active {
        border-color: var(--accent);
        box-shadow: 0 0 0 2px rgba(15, 118, 110, .13);
      }
      .palette-button {
        display: grid;
        grid-template-columns: 30px 1fr;
        gap: 9px;
        align-items: center;
        width: 100%;
        border: 1px solid var(--line);
        background: var(--field);
        text-align: left;
      }
      .palette-icon {
        display: grid;
        place-items: center;
        width: 30px;
        height: 30px;
        border-radius: 7px;
        background: var(--accent-soft);
        color: var(--accent);
        font-weight: 900;
      }
      .palette-button:nth-child(2n) .palette-icon {
        background: #eee9ff;
        color: var(--violet);
      }
      .palette-button:nth-child(3n) .palette-icon {
        background: #fff2d9;
        color: var(--amber);
      }
      .canvas-shell {
        position: relative;
        overflow: auto;
        background-color: var(--canvas);
        background-image:
          linear-gradient(var(--grid-line) 1px, transparent 1px),
          linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
        background-size: 28px 28px;
      }
      .canvas-stage {
        position: relative;
        width: 2400px;
        height: 1300px;
      }
      .edges {
        position: absolute;
        inset: 0;
        width: 2400px;
        height: 1300px;
        color: var(--edge);
        pointer-events: none;
      }
      .edge-path {
        fill: none;
        stroke: var(--edge);
        stroke-width: 2.2;
        pointer-events: stroke;
        cursor: pointer;
      }
      .edge-path:hover,
      .edge-path.active {
        stroke: var(--accent);
        stroke-width: 3;
      }
      .edge-hit {
        fill: none;
        stroke: transparent;
        stroke-width: 18;
        pointer-events: stroke;
        cursor: pointer;
      }
      .edge-label {
        fill: var(--edge-label-ink);
        font-size: 12px;
        font-weight: 850;
        pointer-events: none;
      }
      .edge-label-bg {
        fill: var(--edge-label-bg);
        stroke: var(--line);
        stroke-width: 1;
        rx: 7;
        filter: drop-shadow(0 3px 8px rgba(0, 0, 0, .18));
      }
      .draft-edge {
        fill: none;
        stroke: var(--accent);
        stroke-dasharray: 6 6;
        stroke-width: 2.5;
      }
      .node {
        position: absolute;
        width: var(--node-w);
        min-height: var(--node-h);
        border: 1px solid var(--line-strong);
        border-radius: 8px;
        background: var(--panel);
        box-shadow: 0 1px 2px rgba(16, 24, 40, .06);
        cursor: grab;
        user-select: none;
      }
      .node:active { cursor: grabbing; }
      .node.selected {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px rgba(15, 118, 110, .16), var(--shadow);
      }
      .node.running {
        border-color: var(--violet);
      }
      .node-head {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 11px 12px 8px;
        cursor: grab;
      }
      .node-head:active { cursor: grabbing; }
      .node-badge {
        display: grid;
        place-items: center;
        flex: 0 0 auto;
        width: 34px;
        height: 34px;
        border-radius: 8px;
        background: var(--accent-soft);
        color: var(--accent);
        font-weight: 900;
      }
      .node:nth-of-type(3n) .node-badge {
        background: #eee9ff;
        color: var(--violet);
      }
      .node-title {
        overflow: hidden;
        font-size: 13px;
        font-weight: 850;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .node-type {
        overflow: hidden;
        color: var(--muted);
        font-size: 11px;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .node-body {
        display: grid;
        gap: 6px;
        padding: 0 12px 12px;
      }
      .node-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
      }
      .chip {
        max-width: 112px;
        overflow: hidden;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 3px 7px;
        background: var(--panel-2);
        color: #425064;
        font-size: 10px;
        font-weight: 750;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .approval {
        color: var(--amber);
      }
      .port {
        position: absolute;
        top: 50%;
        z-index: 3;
        width: 14px;
        height: 14px;
        border: 2px solid #fff;
        border-radius: 50%;
        background: var(--accent);
        box-shadow: 0 0 0 1px var(--accent);
        transform: translateY(-50%);
        cursor: crosshair;
      }
      .port.in { left: -7px; }
      .port.out { right: -7px; }
      .port:hover {
        width: 18px;
        height: 18px;
        transform: translateY(-50%) translateX(0);
      }
      .field { display: grid; gap: 6px; }
      .panel-block {
        border-top: 1px solid var(--line);
        margin-top: 14px;
        padding-top: 14px;
      }
      .status {
        min-height: 18px;
        color: var(--muted);
        font-size: 12px;
        line-height: 1.4;
      }
      pre {
        max-height: 280px;
        min-height: 140px;
        overflow: auto;
        margin: 0;
        border-radius: 7px;
        background: #111827;
        color: #e5e7eb;
        padding: 12px;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .edge-row {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr auto;
        gap: 6px;
      }
      @media (max-width: 1180px) {
        body { overflow: auto; }
        .app {
          grid-template-columns: 240px minmax(520px, 1fr);
          height: auto;
          min-height: 100vh;
        }
        .right {
          grid-column: 1 / -1;
          border-width: 1px 0 0;
        }
        .canvas-shell { height: 620px; }
      }
    </style>
  </head>
  <body>
    <main class="app">
      <aside class="left">
        <p class="brand">Agentic Nodes</p>
        <p class="subtle">Config workflow editor</p>

        <section class="section">
          <p class="section-title">Workflows</p>
          <div id="workflow-list" class="stack"></div>
        </section>

        <section class="section">
          <p class="section-title">Node Palette</p>
          <div id="node-palette" class="stack"></div>
        </section>

        <section class="section">
          <p class="section-title">Actions</p>
          <div class="stack">
            <button class="primary" id="run-button" type="button">Run</button>
            <button class="secondary" id="save-button" type="button">Save</button>
            <button class="secondary" id="new-button" type="button">New Draft</button>
            <button class="secondary" id="copy-button" type="button">Copy JSON</button>
            <button class="secondary" id="load-json-button" type="button">Load JSON</button>
            <button class="secondary" id="layout-button" type="button">Auto Layout</button>
            <button class="secondary" id="reload-button" type="button">Reload</button>
          </div>
          <p id="status" class="status"></p>
        </section>
      </aside>

      <section class="workspace">
        <header class="topbar">
          <div class="title">
            <h1 id="workflow-title">Loading...</h1>
            <div id="workflow-description" class="subtle"></div>
          </div>
          <div class="row">
            <button class="secondary" id="delete-edge-button" type="button">Delete Edge</button>
            <button class="secondary" id="theme-button" type="button">Light Mode</button>
            <button class="secondary" id="docs-button" type="button">API Docs</button>
          </div>
        </header>
        <div id="canvas-shell" class="canvas-shell">
          <div id="canvas-stage" class="canvas-stage">
            <svg id="edges" class="edges" aria-label="Workflow edges"></svg>
            <div id="nodes"></div>
          </div>
        </div>
      </section>

      <aside class="right">
        <div class="stack">
          <div class="field">
            <label for="workflow-name">Workflow Name</label>
            <input id="workflow-name" />
          </div>
          <div class="field">
            <label for="workflow-description-input">Description</label>
            <textarea id="workflow-description-input"></textarea>
          </div>
          <div class="field">
            <label for="entrypoint">Entrypoint</label>
            <select id="entrypoint"></select>
          </div>
        </div>

        <section class="panel-block">
          <label>Selected Node</label>
          <p id="empty-node" class="subtle">Select a block on the canvas.</p>
          <div id="node-editor" class="stack" hidden>
            <div class="field">
              <label for="node-id">ID</label>
              <input id="node-id" />
            </div>
            <div class="row">
              <div class="field" style="flex:1">
                <label for="node-type">Type</label>
                <input id="node-type" />
              </div>
              <div class="field" style="flex:1">
                <label for="node-provider">Provider</label>
                <input id="node-provider" />
              </div>
            </div>
            <div class="field">
              <label for="node-model">Model</label>
              <input id="node-model" />
            </div>
            <div class="field">
              <label for="node-prompt">System Prompt</label>
              <textarea id="node-prompt"></textarea>
            </div>
            <div class="row">
              <div class="field" style="flex:1">
                <label for="node-inputs">Input Keys</label>
                <input id="node-inputs" placeholder="comma,separated" />
              </div>
              <div class="field" style="flex:1">
                <label for="node-outputs">Output Keys</label>
                <input id="node-outputs" placeholder="comma,separated" />
              </div>
            </div>
            <div class="field">
              <label for="node-tools">Tools / MCPs</label>
              <input id="node-tools" placeholder="tnt_cli, filesystem_mcp" />
            </div>
            <label class="row" style="justify-content:flex-start">
              <input id="node-approval" type="checkbox" style="width:auto" />
              <span>Human approval required</span>
            </label>
            <button class="danger" id="delete-node-button" type="button">Delete Node</button>
          </div>
        </section>

        <section class="panel-block">
          <label>Edges</label>
          <div id="edge-list" class="stack"></div>
        </section>

        <section class="panel-block">
          <div class="field">
            <label for="clipboard-json">Workflow JSON</label>
            <textarea id="clipboard-json" style="min-height:130px"></textarea>
          </div>
        </section>

        <section class="panel-block">
          <div class="field">
            <label for="run-input">Run Input</label>
            <textarea id="run-input" style="min-height:112px">{
  "inputs": {
    "requirements_doc": "examples/checkout_requirements.md",
    "source_path": "examples/mock_checkout_app",
    "coverage_strength": 2,
    "target_test_framework": "pytest"
  }
}</textarea>
          </div>
          <div class="field">
            <label for="run-output">Run Output</label>
            <pre id="run-output">No run yet.</pre>
          </div>
        </section>
      </aside>
    </main>

    <script>
      const NODE_W = 264;
      const NODE_H = 122;
      const PALETTE = [
        ["doc_reader", "Doc", "Read docs and requirements"],
        ["source_reader", "Src", "Read repository source"],
        ["variable_extractor", "Var", "Extract variables"],
        ["variable_classifier", "Cls", "Classify variables"],
        ["domain_generator", "Dom", "Generate domains"],
        ["constraint_builder", "Con", "Build constraints"],
        ["tnt_cli_reducer", "TnT", "Reduce test matrix"],
        ["test_writer", "Test", "Write tests"],
        ["test_validator", "Val", "Validate tests"],
        ["test_runner", "Run", "Run tests"],
        ["report_generator", "Rpt", "Generate report"],
      ];

      const $ = (id) => document.getElementById(id);
      const els = {
        workflows: $("workflow-list"),
        palette: $("node-palette"),
        title: $("workflow-title"),
        description: $("workflow-description"),
        shell: $("canvas-shell"),
        stage: $("canvas-stage"),
        edges: $("edges"),
        nodes: $("nodes"),
        status: $("status"),
        workflowName: $("workflow-name"),
        workflowDescriptionInput: $("workflow-description-input"),
        entrypoint: $("entrypoint"),
        emptyNode: $("empty-node"),
        nodeEditor: $("node-editor"),
        nodeId: $("node-id"),
        nodeType: $("node-type"),
        nodeProvider: $("node-provider"),
        nodeModel: $("node-model"),
        nodePrompt: $("node-prompt"),
        nodeInputs: $("node-inputs"),
        nodeOutputs: $("node-outputs"),
        nodeTools: $("node-tools"),
        nodeApproval: $("node-approval"),
        edgeList: $("edge-list"),
        clipboardJson: $("clipboard-json"),
        runInput: $("run-input"),
        runOutput: $("run-output"),
        themeButton: $("theme-button"),
      };

      let workflow = null;
      let selectedWorkflowName = null;
      let selectedNodeId = null;
      let selectedEdgeIndex = null;
      let drag = null;
      let connection = null;

      function applyTheme(theme) {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem("agenticWorkflowTheme", theme);
        els.themeButton.textContent = theme === "dark" ? "Light Mode" : "Dark Mode";
      }

      function toggleTheme() {
        applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
      }

      async function api(path, options = {}) {
        const response = await fetch(path, options);
        if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
        return response.json();
      }

      function setStatus(message) {
        els.status.textContent = message;
      }

      function normalizeWorkflow(nextWorkflow) {
        const nodes = (nextWorkflow.nodes || []).map((node, index) => ({
          id: node.id || `node_${index + 1}`,
          type: node.type || "doc_reader",
          model: node.model || "mock-deterministic",
          provider: node.provider || "mock",
          system_prompt: node.system_prompt || "",
          input_keys: node.input_keys || [],
          output_keys: node.output_keys || [],
          tools: node.tools || [],
          mcps: node.mcps || [],
          retry_policy: node.retry_policy || {max_attempts: 1, backoff_seconds: 0},
          human_approval: Boolean(node.human_approval),
          config: node.config || {},
        }));
        nodes.forEach((node, index) => {
          node.config = node.config || {};
          node.config.ui = node.config.ui || {};
          if (!Number.isFinite(node.config.ui.x) || !Number.isFinite(node.config.ui.y)) {
            node.config.ui.x = 120 + index * 330;
            node.config.ui.y = 170 + (index % 2) * 180;
          }
        });
        return {
          name: nextWorkflow.name || "draft_workflow",
          version: String(nextWorkflow.version || "0.1.0"),
          description: nextWorkflow.description || "",
          entrypoint: nextWorkflow.entrypoint || nodes[0]?.id || "",
          nodes,
          edges: nextWorkflow.edges || [],
        };
      }

      async function loadWorkflows() {
        const data = await api("/workflows");
        els.workflows.innerHTML = "";
        data.workflows.forEach((name) => {
          const button = document.createElement("button");
          button.className = `workflow-button ${name === selectedWorkflowName ? "active" : ""}`;
          button.textContent = name;
          button.type = "button";
          button.onclick = () => loadWorkflow(name);
          els.workflows.appendChild(button);
        });
        if (!selectedWorkflowName && data.workflows.length) {
          await loadWorkflow(data.workflows.includes("starter_three_node") ? "starter_three_node" : data.workflows[0]);
        }
      }

      async function loadWorkflow(name) {
        workflow = normalizeWorkflow(await api(`/workflows/${name}`));
        selectedWorkflowName = name;
        selectedNodeId = workflow.nodes[0]?.id || null;
        selectedEdgeIndex = null;
        renderAll();
        centerCanvasOnWorkflow();
        setStatus(`Loaded ${name}`);
      }

      function renderAll() {
        if (!workflow) return;
        els.title.textContent = workflow.name;
        els.description.textContent = workflow.description;
        els.workflowName.value = workflow.name;
        els.workflowDescriptionInput.value = workflow.description;
        renderWorkflowListSelection();
        renderEntrypoint();
        renderPalette();
        renderNodes();
        renderEdges();
        renderNodeEditor();
        renderEdgeList();
        syncClipboard();
      }

      function renderWorkflowListSelection() {
        [...els.workflows.children].forEach((button) => {
          button.classList.toggle("active", button.textContent === selectedWorkflowName);
        });
      }

      function renderPalette() {
        if (els.palette.childElementCount) return;
        PALETTE.forEach(([type, icon, description]) => {
          const button = document.createElement("button");
          button.className = "palette-button";
          button.type = "button";
          button.innerHTML = `<span class="palette-icon">${escapeHtml(icon)}</span><span><strong>${escapeHtml(type)}</strong><br><span class="subtle">${escapeHtml(description)}</span></span>`;
          button.onclick = () => addNode(type);
          els.palette.appendChild(button);
        });
      }

      function renderEntrypoint() {
        els.entrypoint.innerHTML = "";
        workflow.nodes.forEach((node) => {
          const option = document.createElement("option");
          option.value = node.id;
          option.textContent = node.id;
          option.selected = node.id === workflow.entrypoint;
          els.entrypoint.appendChild(option);
        });
      }

      function renderNodes() {
        els.nodes.innerHTML = "";
        workflow.nodes.forEach((node) => {
          const element = document.createElement("div");
          element.className = `node ${node.id === selectedNodeId ? "selected" : ""}`;
          element.style.left = `${node.config.ui.x}px`;
          element.style.top = `${node.config.ui.y}px`;
          element.dataset.nodeId = node.id;
          element.innerHTML = `
            <div class="port in" data-target-port="${escapeHtml(node.id)}" title="Input"></div>
            <div class="port out" data-source-port="${escapeHtml(node.id)}" title="Output"></div>
            <div class="node-head" data-drag-node="${escapeHtml(node.id)}">
              <div class="node-badge">${escapeHtml(shortType(node.type))}</div>
              <div style="min-width:0">
                <div class="node-title">${escapeHtml(node.id)}</div>
                <div class="node-type">${escapeHtml(node.type)} · ${escapeHtml(node.provider || "default")}</div>
              </div>
            </div>
            <div class="node-body">
              <div class="node-chip-row">
                ${node.model ? `<span class="chip">${escapeHtml(node.model)}</span>` : ""}
                ${node.tools.slice(0, 2).map((tool) => `<span class="chip">${escapeHtml(tool)}</span>`).join("")}
                ${node.human_approval ? `<span class="chip approval">approval</span>` : ""}
              </div>
              <div class="subtle">${escapeHtml((node.system_prompt || "No prompt yet.").slice(0, 86))}</div>
            </div>
          `;
          element.onclick = (event) => {
            if (event.target.closest(".port")) return;
            selectedNodeId = node.id;
            selectedEdgeIndex = null;
            renderAll();
          };
          els.nodes.appendChild(element);
        });
        bindNodeInteractions();
      }

      function renderEdges() {
        clearSvg();
        const marker = svg("marker", {id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse"});
        marker.appendChild(svg("path", {d: "M 0 0 L 10 5 L 0 10 z", fill: "var(--edge)"}));
        const defs = svg("defs");
        defs.appendChild(marker);
        els.edges.appendChild(defs);

        workflow.edges.forEach((edge, index) => {
          const points = edgePoints(edge);
          if (!points) return;
          const path = bezier(points.source, points.target);
          const hit = svg("path", {class: "edge-hit", d: path});
          const visible = svg("path", {
            class: `edge-path ${index === selectedEdgeIndex ? "active" : ""}`,
            d: path,
            "marker-end": "url(#arrow)",
          });
          [hit, visible].forEach((pathElement) => {
            pathElement.onclick = (event) => {
              event.stopPropagation();
              selectedEdgeIndex = index;
              selectedNodeId = null;
              renderAll();
            };
          });
          els.edges.appendChild(hit);
          els.edges.appendChild(visible);
          const label = readableEdgeLabel(edge);
          const midX = (points.source.x + points.target.x) / 2;
          const midY = (points.source.y + points.target.y) / 2 - 16;
          const displayLabel = label.length > 42 ? `${label.slice(0, 39)}...` : label;
          const labelWidth = Math.min(360, Math.max(104, displayLabel.length * 7.4 + 26));
          const group = svg("g");
          group.setAttribute("style", "pointer-events: auto; cursor: pointer;");
          const rect = svg("rect", {
            class: "edge-label-bg",
            x: midX - labelWidth / 2,
            y: midY - 17,
            width: labelWidth,
            height: 26,
          });
          const text = svg("text", {class: "edge-label", x: midX, y: midY, "text-anchor": "middle"});
          text.textContent = displayLabel;
          group.appendChild(rect);
          group.appendChild(text);
          group.onclick = (event) => {
            event.stopPropagation();
            selectedEdgeIndex = index;
            selectedNodeId = null;
            renderAll();
          };
          els.edges.appendChild(group);
        });

        if (connection) {
          const source = outputPoint(connection.sourceId);
          const draft = svg("path", {class: "draft-edge", d: bezier(source, connection.pointer)});
          els.edges.appendChild(draft);
        }
      }

      function renderNodeEditor() {
        const node = getSelectedNode();
        els.emptyNode.hidden = Boolean(node);
        els.nodeEditor.hidden = !node;
        if (!node) return;
        els.nodeId.value = node.id;
        els.nodeType.value = node.type;
        els.nodeProvider.value = node.provider || "";
        els.nodeModel.value = node.model || "";
        els.nodePrompt.value = node.system_prompt || "";
        els.nodeInputs.value = node.input_keys.join(", ");
        els.nodeOutputs.value = node.output_keys.join(", ");
        els.nodeTools.value = node.tools.join(", ");
        els.nodeApproval.checked = node.human_approval;
      }

      function renderEdgeList() {
        els.edgeList.innerHTML = "";
        workflow.edges.forEach((edge, index) => {
          const row = document.createElement("div");
          row.className = "edge-row";
          row.innerHTML = `
            <select data-edge-source="${index}">${nodeOptions(edge.source)}</select>
            <select data-edge-target="${index}">${nodeOptions(edge.target)}</select>
            <input data-edge-label="${index}" value="${escapeHtml(edge.label || "")}" placeholder="edge label" />
            <button class="danger" data-edge-delete="${index}" type="button">Remove</button>
          `;
          els.edgeList.appendChild(row);
        });
        els.edgeList.querySelectorAll("[data-edge-source]").forEach((select) => {
          select.onchange = () => {
            workflow.edges[Number(select.dataset.edgeSource)].source = select.value;
            renderAll();
          };
        });
        els.edgeList.querySelectorAll("[data-edge-target]").forEach((select) => {
          select.onchange = () => {
            workflow.edges[Number(select.dataset.edgeTarget)].target = select.value;
            renderAll();
          };
        });
        els.edgeList.querySelectorAll("[data-edge-label]").forEach((input) => {
          input.oninput = () => {
            workflow.edges[Number(input.dataset.edgeLabel)].label = input.value;
            renderEdges();
            syncClipboard();
          };
        });
        els.edgeList.querySelectorAll("[data-edge-delete]").forEach((button) => {
          button.onclick = () => {
            workflow.edges.splice(Number(button.dataset.edgeDelete), 1);
            selectedEdgeIndex = null;
            renderAll();
          };
        });
      }

      function bindNodeInteractions() {
        els.nodes.querySelectorAll("[data-node-id]").forEach((handle) => {
          handle.onpointerdown = (event) => {
            if (event.target.closest(".port")) return;
            const node = workflow.nodes.find((item) => item.id === handle.dataset.nodeId);
            if (!node) return;
            selectedNodeId = node.id;
            selectedEdgeIndex = null;
            drag = {
              nodeId: node.id,
              startX: event.clientX,
              startY: event.clientY,
              originalX: node.config.ui.x,
              originalY: node.config.ui.y,
            };
            handle.setPointerCapture(event.pointerId);
          };
        });
        els.nodes.querySelectorAll("[data-source-port]").forEach((port) => {
          port.onpointerdown = (event) => {
            event.stopPropagation();
            const sourceId = port.dataset.sourcePort;
            connection = {sourceId, pointer: canvasPoint(event)};
            document.addEventListener("pointermove", onConnectionMove);
            document.addEventListener("pointerup", onConnectionEnd, {once: true});
            renderEdges();
          };
        });
      }

      document.addEventListener("pointermove", (event) => {
        if (!drag) return;
        const node = workflow.nodes.find((item) => item.id === drag.nodeId);
        if (!node) return;
        node.config.ui.x = Math.max(40, drag.originalX + event.clientX - drag.startX);
        node.config.ui.y = Math.max(40, drag.originalY + event.clientY - drag.startY);
        const element = [...els.nodes.children].find((candidate) => candidate.dataset.nodeId === node.id);
        if (element) {
          element.style.left = `${node.config.ui.x}px`;
          element.style.top = `${node.config.ui.y}px`;
        }
        renderEdges();
        syncClipboard();
      });

      document.addEventListener("pointerup", () => {
        if (drag) {
          drag = null;
          renderAll();
        }
      });

      function onConnectionMove(event) {
        if (!connection) return;
        connection.pointer = canvasPoint(event);
        renderEdges();
      }

      function onConnectionEnd(event) {
        document.removeEventListener("pointermove", onConnectionMove);
        if (!connection) return;
        const targetElement = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-target-port]");
        const targetId = targetElement?.dataset.targetPort;
        if (targetId && targetId !== connection.sourceId) {
          const exists = workflow.edges.some((edge) => edge.source === connection.sourceId && edge.target === targetId);
          if (!exists) {
            workflow.edges.push({source: connection.sourceId, target: targetId, label: defaultEdgeLabel(connection.sourceId, targetId)});
            selectedEdgeIndex = workflow.edges.length - 1;
            selectedNodeId = null;
            setStatus(`Connected ${connection.sourceId} -> ${targetId}`);
          }
        }
        connection = null;
        renderAll();
      }

      function applyWorkflowFields() {
        const oldName = workflow.name;
        workflow.name = slugify(els.workflowName.value || "draft_workflow");
        workflow.description = els.workflowDescriptionInput.value;
        workflow.entrypoint = els.entrypoint.value || workflow.nodes[0]?.id || "";
        if (selectedWorkflowName === oldName) selectedWorkflowName = workflow.name;
      }

      function applyNodeFields() {
        const node = getSelectedNode();
        if (!node) return;
        const oldId = node.id;
        const nextId = slugify(els.nodeId.value || oldId);
        node.id = nextId;
        node.type = els.nodeType.value || "doc_reader";
        node.provider = els.nodeProvider.value || null;
        node.model = els.nodeModel.value || null;
        node.system_prompt = els.nodePrompt.value;
        node.input_keys = csv(els.nodeInputs.value);
        node.output_keys = csv(els.nodeOutputs.value);
        node.tools = csv(els.nodeTools.value);
        node.human_approval = els.nodeApproval.checked;
        if (oldId !== nextId) {
          workflow.edges.forEach((edge) => {
            if (edge.source === oldId) edge.source = nextId;
            if (edge.target === oldId) edge.target = nextId;
          });
          if (workflow.entrypoint === oldId) workflow.entrypoint = nextId;
          selectedNodeId = nextId;
        }
      }

      async function saveWorkflow() {
        applyWorkflowFields();
        applyNodeFields();
        workflow = normalizeWorkflow(workflow);
        const ids = workflow.nodes.map((node) => node.id);
        if (new Set(ids).size !== ids.length) throw new Error("Node ids must be unique.");
        await api(`/workflows/${workflow.name}`, {
          method: "PUT",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(workflow),
        });
        selectedWorkflowName = workflow.name;
        await loadWorkflows();
        setStatus(`Saved ${workflow.name}`);
      }

      async function runWorkflow() {
        applyWorkflowFields();
        applyNodeFields();
        els.runOutput.textContent = "Running...";
        try {
          const body = JSON.parse(els.runInput.value);
          const data = await api(`/workflows/${workflow.name}/run`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body),
          });
          els.runOutput.textContent = data.state?.final_report || JSON.stringify(data, null, 2);
          setStatus(`Run ${data.status}: ${data.run_id}`);
        } catch (error) {
          els.runOutput.textContent = error.message;
          setStatus("Run failed");
        }
      }

      function addNode(type = "doc_reader") {
        const id = nextNodeId(type);
        const viewport = {
          x: els.shell.scrollLeft + Math.min(520, els.shell.clientWidth / 2),
          y: els.shell.scrollTop + Math.min(300, els.shell.clientHeight / 2),
        };
        workflow.nodes.push({
          id,
          type,
          model: "mock-deterministic",
          provider: "mock",
          system_prompt: "",
          input_keys: [],
          output_keys: [],
          tools: [],
          mcps: [],
          retry_policy: {max_attempts: 1, backoff_seconds: 0},
          human_approval: false,
          config: {ui: {x: viewport.x, y: viewport.y}},
        });
        if (!workflow.entrypoint) workflow.entrypoint = id;
        selectedNodeId = id;
        selectedEdgeIndex = null;
        renderAll();
      }

      function deleteNode() {
        const node = getSelectedNode();
        if (!node) return;
        workflow.nodes = workflow.nodes.filter((item) => item.id !== node.id);
        workflow.edges = workflow.edges.filter((edge) => edge.source !== node.id && edge.target !== node.id);
        workflow.entrypoint = workflow.nodes.find((item) => item.id === workflow.entrypoint)?.id || workflow.nodes[0]?.id || "";
        selectedNodeId = workflow.nodes[0]?.id || null;
        selectedEdgeIndex = null;
        renderAll();
      }

      function deleteSelectedEdge() {
        if (selectedEdgeIndex === null) return;
        workflow.edges.splice(selectedEdgeIndex, 1);
        selectedEdgeIndex = null;
        renderAll();
      }

      function newDraft() {
        workflow = normalizeWorkflow({
          name: "draft_workflow",
          version: "0.1.0",
          description: "A new config-driven workflow.",
          entrypoint: "start",
          nodes: [{id: "start", type: "doc_reader", provider: "mock", model: "mock-deterministic"}],
          edges: [],
        });
        selectedWorkflowName = null;
        selectedNodeId = "start";
        selectedEdgeIndex = null;
        renderAll();
        setStatus("Created draft");
      }

      function autoLayout() {
        workflow.nodes.forEach((node, index) => {
          node.config.ui.x = 120 + index * 330;
          node.config.ui.y = 180 + (index % 2) * 170;
        });
        renderAll();
        centerCanvasOnWorkflow();
      }

      function loadFromJson() {
        workflow = normalizeWorkflow(JSON.parse(els.clipboardJson.value));
        selectedWorkflowName = workflow.name;
        selectedNodeId = workflow.nodes[0]?.id || null;
        selectedEdgeIndex = null;
        renderAll();
        setStatus("Loaded JSON. Save to persist as YAML.");
      }

      async function copyJson() {
        syncClipboard();
        await navigator.clipboard?.writeText(els.clipboardJson.value).catch(() => {});
        els.clipboardJson.select();
        setStatus("Workflow JSON ready to copy");
      }

      function centerCanvasOnWorkflow() {
        const first = workflow.nodes[0];
        if (!first) return;
        els.shell.scrollLeft = Math.max(0, first.config.ui.x - 160);
        els.shell.scrollTop = Math.max(0, first.config.ui.y - 160);
      }

      function edgePoints(edge) {
        const source = workflow.nodes.find((node) => node.id === edge.source);
        const target = workflow.nodes.find((node) => node.id === edge.target);
        if (!source || !target) return null;
        return {source: outputPoint(source.id), target: inputPoint(target.id)};
      }

      function outputPoint(nodeId) {
        const node = workflow.nodes.find((item) => item.id === nodeId);
        return {x: node.config.ui.x + NODE_W, y: node.config.ui.y + NODE_H / 2};
      }

      function inputPoint(nodeId) {
        const node = workflow.nodes.find((item) => item.id === nodeId);
        return {x: node.config.ui.x, y: node.config.ui.y + NODE_H / 2};
      }

      function bezier(source, target) {
        const distance = Math.max(120, Math.abs(target.x - source.x) * .45);
        return `M ${source.x} ${source.y} C ${source.x + distance} ${source.y}, ${target.x - distance} ${target.y}, ${target.x} ${target.y}`;
      }

      function canvasPoint(event) {
        const rect = els.stage.getBoundingClientRect();
        return {x: event.clientX - rect.left, y: event.clientY - rect.top};
      }

      function getSelectedNode() {
        return workflow?.nodes.find((node) => node.id === selectedNodeId);
      }

      function nodeOptions(selected) {
        return workflow.nodes.map((node) => `<option value="${escapeHtml(node.id)}" ${node.id === selected ? "selected" : ""}>${escapeHtml(node.id)}</option>`).join("");
      }

      function readableEdgeLabel(edge) {
        if (edge.label && edge.label.trim()) return edge.label.trim();
        return defaultEdgeLabel(edge.source, edge.target);
      }

      function defaultEdgeLabel(sourceId, targetId) {
        const source = workflow.nodes.find((node) => node.id === sourceId);
        const target = workflow.nodes.find((node) => node.id === targetId);
        const output = source?.output_keys?.[0] || "state";
        const input = target?.input_keys?.[0] || "input";
        return `${output} -> ${input}`;
      }

      function syncClipboard() {
        els.clipboardJson.value = JSON.stringify(workflow, null, 2);
      }

      function csv(value) {
        return value.split(",").map((item) => item.trim()).filter(Boolean);
      }

      function slugify(value) {
        return String(value).trim().replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "") || "workflow";
      }

      function nextNodeId(type) {
        const base = slugify(type || "node");
        let index = workflow.nodes.length + 1;
        while (workflow.nodes.some((node) => node.id === `${base}_${index}`)) index += 1;
        return `${base}_${index}`;
      }

      function shortType(type) {
        return String(type || "N").split("_").map((part) => part[0]).join("").slice(0, 3).toUpperCase();
      }

      function clearSvg() {
        while (els.edges.firstChild) els.edges.removeChild(els.edges.firstChild);
      }

      function svg(name, attrs = {}) {
        const element = document.createElementNS("http://www.w3.org/2000/svg", name);
        Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
        return element;
      }

      function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, (char) => ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#039;",
        }[char]));
      }

      [
        els.workflowName,
        els.workflowDescriptionInput,
        els.entrypoint,
        els.nodeId,
        els.nodeType,
        els.nodeProvider,
        els.nodeModel,
        els.nodePrompt,
        els.nodeInputs,
        els.nodeOutputs,
        els.nodeTools,
        els.nodeApproval,
      ].forEach((input) => {
        input.oninput = () => {
          applyWorkflowFields();
          applyNodeFields();
          renderAll();
        };
      });

      $("run-button").onclick = () => runWorkflow().catch((error) => setStatus(error.message));
      $("save-button").onclick = () => saveWorkflow().catch((error) => setStatus(error.message));
      $("new-button").onclick = newDraft;
      $("copy-button").onclick = copyJson;
      $("load-json-button").onclick = () => {
        try { loadFromJson(); } catch (error) { setStatus(error.message); }
      };
      $("layout-button").onclick = autoLayout;
      $("reload-button").onclick = () => loadWorkflows().catch((error) => setStatus(error.message));
      $("delete-node-button").onclick = deleteNode;
      $("delete-edge-button").onclick = deleteSelectedEdge;
      $("theme-button").onclick = toggleTheme;
      $("docs-button").onclick = () => window.open("/docs", "_blank");
      applyTheme(document.documentElement.dataset.theme || "dark");
      els.edges.onclick = () => {
        selectedEdgeIndex = null;
        renderAll();
      };
      els.stage.onclick = (event) => {
        if (event.target === els.stage || event.target === els.nodes || event.target === els.edges) {
          selectedNodeId = null;
          selectedEdgeIndex = null;
          renderAll();
        }
      };

      loadWorkflows().catch((error) => {
        newDraft();
        workflow.name = "starter_three_node_local";
        workflow.description = "Local fallback starter workflow. The API failed to load saved workflows.";
        workflow.nodes[0].config.ui = {x: 140, y: 260};
        workflow.nodes.push({
          id: "variable_extractor",
          type: "variable_extractor",
          model: "mock-deterministic",
          provider: "mock",
          system_prompt: "Extract variables from the document summary.",
          input_keys: ["doc_reader"],
          output_keys: ["variables"],
          tools: [],
          mcps: [],
          retry_policy: {max_attempts: 1, backoff_seconds: 0},
          human_approval: false,
          config: {ui: {x: 500, y: 260}},
        });
        workflow.nodes[0].id = "doc_reader";
        workflow.nodes[0].type = "doc_reader";
        workflow.nodes[0].output_keys = ["documents"];
        workflow.entrypoint = "doc_reader";
        workflow.nodes.push({
          id: "report_generator",
          type: "report_generator",
          model: "mock-deterministic",
          provider: "mock",
          system_prompt: "Produce a short markdown report.",
          input_keys: ["variables"],
          output_keys: ["final_report"],
          tools: [],
          mcps: [],
          retry_policy: {max_attempts: 1, backoff_seconds: 0},
          human_approval: false,
          config: {ui: {x: 860, y: 260}},
        });
        workflow.edges = [
          {source: "doc_reader", target: "variable_extractor", label: "documents"},
          {source: "variable_extractor", target: "report_generator", label: "variables"},
        ];
        selectedNodeId = "doc_reader";
        renderAll();
        setStatus(error.message);
      });
    </script>
  </body>
</html>
"""


async def workflow_editor() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)
