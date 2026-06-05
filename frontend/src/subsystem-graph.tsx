import React, { useEffect, useMemo, useRef, useState } from "react";

type GraphResponse = {
  mermaid: string;
  actions: string[];
  entrypoint: string;
  transitions: Array<{ from: string; to: string; condition: string }>;
  node_id_map: Record<string, string>;
};

type Props = {
  workflowName: string;
  nodeId: string;
  currentAction?: string | null;
};

let mermaidModulePromise: Promise<typeof import("mermaid").default> | null = null;

function loadMermaid() {
  if (mermaidModulePromise === null) {
    mermaidModulePromise = import("mermaid").then((mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        themeVariables: {
          primaryColor: "#1e3a8a",
          primaryTextColor: "#e2e8f0",
          primaryBorderColor: "#475569",
          lineColor: "#94a3b8",
        },
      });
      return mermaid;
    });
  }
  return mermaidModulePromise;
}

/**
 * Mermaid runtime visualizer for a Burr subsystem.
 *
 * Loads the static graph once from the backend, then re-renders with a
 * `current` class applied to whichever action the parent reports as live.
 */
export function SubsystemGraphPanel({ workflowName, nodeId, currentAction }: Props) {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setGraph(null);
    const url = `/workflows/${encodeURIComponent(workflowName)}/subsystems/${encodeURIComponent(nodeId)}/graph`;
    fetch(url)
      .then(async (resp) => {
        if (!resp.ok) {
          const detail = await resp.text();
          throw new Error(`HTTP ${resp.status}: ${detail.slice(0, 200)}`);
        }
        return resp.json() as Promise<GraphResponse>;
      })
      .then((data) => {
        if (!cancelled) {
          setGraph(data);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(String(err.message ?? err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [workflowName, nodeId]);

  const decoratedSource = useMemo(() => {
    if (!graph) {
      return "";
    }
    if (!currentAction) {
      return graph.mermaid;
    }
    const currentNodeId = graph.node_id_map[currentAction];
    if (!currentNodeId) {
      return graph.mermaid;
    }
    return `${graph.mermaid}\n    class ${currentNodeId} current`;
  }, [graph, currentAction]);

  useEffect(() => {
    if (!decoratedSource || !containerRef.current) {
      return;
    }
    let cancelled = false;
    const target = containerRef.current;
    target.innerHTML = "";
    const id = `subsystem-graph-${Math.random().toString(36).slice(2, 10)}`;
    loadMermaid()
      .then(async (mermaid) => {
        if (cancelled) return;
        const { svg } = await mermaid.render(id, decoratedSource);
        if (!cancelled) {
          target.innerHTML = svg;
        }
      })
      .catch((err) => {
        if (!cancelled) {
          target.innerHTML = `<pre class="mermaid-error">Mermaid render failed: ${err}</pre>`;
        }
      });
    return () => {
      cancelled = true;
    };
  }, [decoratedSource]);

  if (error) {
    return (
      <div className="subsystem-graph subsystem-graph-error">
        <strong>Subsystem graph unavailable</strong>
        <p>{error}</p>
      </div>
    );
  }
  if (!graph) {
    return <div className="subsystem-graph subsystem-graph-loading">Loading subsystem graph…</div>;
  }
  return (
    <div className="subsystem-graph">
      <div className="subsystem-graph-header">
        <strong>Runtime graph</strong>
        <span>
          {currentAction ? `current: ${currentAction}` : `entry: ${graph.entrypoint || "(none)"}`}
        </span>
      </div>
      <div className="subsystem-graph-canvas" ref={containerRef} />
    </div>
  );
}
