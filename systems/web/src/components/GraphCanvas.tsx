"use client";

import { useMemo } from "react";
import type { KnowledgeGraph } from "@/lib/types";

// Deterministic two-ring layout: dimension nodes on an inner ring, actor nodes
// on an outer ring (grouped by category order). Reliable + legible without a
// force-simulation dependency.
export default function GraphCanvas({ graph }: { graph: KnowledgeGraph }) {
  const { positioned, edges, W, H } = useMemo(() => {
    const W = 900;
    const H = 620;
    const cx = W / 2;
    const cy = H / 2;
    const actors = graph.nodes.filter((n) => n.kind === "actor");
    const dims = graph.nodes.filter((n) => n.kind === "dimension");
    const pos = new Map<string, { x: number; y: number }>();

    const place = (arr: typeof graph.nodes, r: number) => {
      arr.forEach((n, i) => {
        const ang = (i / Math.max(1, arr.length)) * Math.PI * 2 - Math.PI / 2;
        pos.set(n.id, { x: cx + r * Math.cos(ang), y: cy + r * Math.sin(ang) });
      });
    };
    place(dims, 120);
    place(actors, 270);

    const positioned = graph.nodes.map((n) => ({ ...n, ...(pos.get(n.id) || { x: cx, y: cy }) }));
    const edges = graph.edges.map((e) => ({
      ...e,
      a: pos.get(e.source),
      b: pos.get(e.target),
    }));
    return { positioned, edges, W, H };
  }, [graph]);

  if (!graph.nodes.length) return <div className="empty">No graph for this window.</div>;

  return (
    <div style={{ width: "100%", overflowX: "auto" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", minWidth: 600 }}>
        {edges.map((e, i) =>
          e.a && e.b ? (
            <line
              key={i}
              x1={e.a.x}
              y1={e.a.y}
              x2={e.b.x}
              y2={e.b.y}
              stroke={e.kind === "actor-actor" ? "#c7d2fe" : "#e2e6ee"}
              strokeWidth={e.kind === "actor-actor" ? Math.min(4, 1 + e.weight) : 1}
            />
          ) : null
        )}
        {positioned.map((n) => (
          <g key={n.id}>
            <circle cx={n.x} cy={n.y} r={n.kind === "actor" ? Math.min(18, n.size / 2) : 7} fill={n.color} opacity={n.kind === "actor" ? 0.9 : 0.6}>
              <title>{n.label}</title>
            </circle>
            {n.kind === "actor" && (
              <text x={n.x} y={n.y - (Math.min(18, n.size / 2) + 4)} textAnchor="middle" fontSize={10} fill="#0f1729">
                {n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label}
              </text>
            )}
            {n.kind === "dimension" && (
              <text x={n.x} y={n.y + 16} textAnchor="middle" fontSize={9} fill="#5b6678">
                {n.label}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}
