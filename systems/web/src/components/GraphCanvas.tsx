"use client";

import { useMemo, useState } from "react";
import type { KnowledgeGraph, KnowledgeGraphEdge, KnowledgeGraphNode } from "@/lib/types";

/**
 * Knowledge-graph SVG renderer.
 *
 * The earlier two-ring layout failed at our actual data volume (30 actors,
 * 9 dimensions, ~400 edges). Three things made it unreadable:
 *
 *   1. ALL actor-dim edges went through the centre as straight lines, so
 *      the middle of the chart was an opaque tangle of ~120 crossings.
 *   2. The 288 actor-actor edges dominated the foreground.
 *   3. Outer-ring labels were horizontal at 10pt — adjacent actors'
 *      labels stacked on top of each other 30 times around the ring.
 *
 * v0.4.0 additions:
 *   - Inspector panel (top-right of the canvas) updates on node OR edge
 *     hover with the semantic meaning of what you're hovering. For
 *     actor-dim edges this shows the dimension label, count, and up to
 *     3 sample signal titles; for actor-actor edges the shared signal
 *     types + shared dimensions; for nodes a list of connected
 *     dimensions / actors with counts. Backed by the enriched
 *     /api/knowledge-graph payload — no second round-trip.
 *   - Native SVG <title> on every edge path as an accessibility / right-
 *     click fallback; tooltip text uses the same enrichment fields.
 *
 * Still dependency-free — same architectural choice as the rest of the site.
 */

type Positioned = KnowledgeGraphNode & {
  x: number;
  y: number;
  angle: number; // radians, used for tangential label rotation
};

// v0.4.40 — widened to admit the three additive edge kinds. Unknown
// kinds are kept as `actor-dim`-shaped (no-op rendering branch).
type EdgeKind =
  | "actor-dim"
  | "actor-actor"
  | "dim-signal-type"
  | "actor-signal-type"
  | "actor-actor-sim";

type EdgePositioned = KnowledgeGraphEdge & {
  kind: EdgeKind;
  a: { x: number; y: number };
  b: { x: number; y: number };
};

// Geometry tuned for ~30 actors + ~9 dimensions; gracefully degrades for less.
const W = 1100;
const H = 800;
const CX = W / 2;
const CY = H / 2;
const RING_SIGNAL_TYPE = 80;   // v0.4.40 — inner-most ring (only used when taxonomy is on)
const RING_DIM = 200;
const RING_ACTOR = 330;
const CATEGORY_GAP_DEG = 6;

// Stable display order for the 4 Ehrenthal signal_type nodes — matches
// the order used elsewhere on the dashboard (api/main.py ORDER list).
const SIGNAL_TYPE_ORDER = [
  "legitimacy",
  "customer_cocreation",
  "community_ecosystem",
  "future_trajectory",
];

const isKnownEdgeKind = (k: string): k is EdgeKind =>
  k === "actor-dim" ||
  k === "actor-actor" ||
  k === "dim-signal-type" ||
  k === "actor-signal-type" ||
  k === "actor-actor-sim";

const CATEGORY_ORDER = [
  "national_initiative",
  "university_or_research_hub",
  "private_company",
  "ecosystem_builder",
  "government",
];

// What the inspector is currently showing. `null` = nothing (or the default).
type Inspect =
  | { kind: "node"; nodeId: string }
  | { kind: "edge"; edgeIndex: number }
  | null;

export default function GraphCanvas({ graph }: { graph: KnowledgeGraph }) {
  const [inspect, setInspect] = useState<Inspect>(null);
  const [showPeerEdges, setShowPeerEdges] = useState(false);

  const { actorNodes, dimNodes, signalTypeNodes, edges, neighbours, nodeById } = useMemo(() => {
    const actorsRaw = graph.nodes.filter((n) => n.kind === "actor");
    const dimsRaw = graph.nodes.filter((n) => n.kind === "dimension");
    // v0.4.40 — opt-in signal_type nodes go on an inner-most ring.
    // Empty array when include_taxonomy=false (the default).
    const signalTypesRaw = graph.nodes.filter((n) => n.kind === "signal_type");

    const catRank = (c: string) => {
      const idx = CATEGORY_ORDER.indexOf(c);
      return idx === -1 ? CATEGORY_ORDER.length : idx;
    };
    const actorsSorted = [...actorsRaw].sort((a, b) => {
      const ca = a.category || "";
      const cb = b.category || "";
      if (ca !== cb) return catRank(ca) - catRank(cb) || ca.localeCompare(cb);
      return a.label.localeCompare(b.label);
    });

    const groupCounts: { cat: string; count: number }[] = [];
    for (const a of actorsSorted) {
      const c = a.category || "";
      const last = groupCounts[groupCounts.length - 1];
      if (last && last.cat === c) last.count += 1;
      else groupCounts.push({ cat: c, count: 1 });
    }
    const totalGap = (groupCounts.length * CATEGORY_GAP_DEG * Math.PI) / 180;
    const usableArc = Math.PI * 2 - totalGap;
    const perActor = usableArc / Math.max(1, actorsSorted.length);

    let theta = -Math.PI / 2;
    const actorPositions: Positioned[] = [];
    let actorIdx = 0;
    for (const g of groupCounts) {
      for (let i = 0; i < g.count; i++) {
        const ang = theta + perActor * (i + 0.5);
        const a = actorsSorted[actorIdx++];
        actorPositions.push({
          ...a,
          x: CX + RING_ACTOR * Math.cos(ang),
          y: CY + RING_ACTOR * Math.sin(ang),
          angle: ang,
        });
      }
      theta += perActor * g.count + (CATEGORY_GAP_DEG * Math.PI) / 180;
    }

    const dimPositions: Positioned[] = dimsRaw.map((d, i) => {
      const ang = (i / Math.max(1, dimsRaw.length)) * Math.PI * 2 - Math.PI / 2;
      return {
        ...d,
        x: CX + RING_DIM * Math.cos(ang),
        y: CY + RING_DIM * Math.sin(ang),
        angle: ang,
      };
    });

    // v0.4.40 — signal_type ring at fixed angular slots in canonical order.
    const orderedSt = [...signalTypesRaw].sort((a, b) => {
      const ka = a.signal_type_key || "";
      const kb = b.signal_type_key || "";
      const ia = SIGNAL_TYPE_ORDER.indexOf(ka);
      const ib = SIGNAL_TYPE_ORDER.indexOf(kb);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
    const signalTypePositions: Positioned[] = orderedSt.map((s, i) => {
      const ang = (i / Math.max(1, orderedSt.length)) * Math.PI * 2 - Math.PI / 2;
      return {
        ...s,
        x: CX + RING_SIGNAL_TYPE * Math.cos(ang),
        y: CY + RING_SIGNAL_TYPE * Math.sin(ang),
        angle: ang,
      };
    });

    const posMap = new Map<string, { x: number; y: number }>();
    for (const n of [...actorPositions, ...dimPositions, ...signalTypePositions]) {
      posMap.set(n.id, { x: n.x, y: n.y });
    }

    const edgesP: EdgePositioned[] = graph.edges
      .map((e) => {
        const a = posMap.get(e.source);
        const b = posMap.get(e.target);
        if (!a || !b) return null;
        const kind: EdgeKind = isKnownEdgeKind(e.kind) ? e.kind : "actor-dim";
        return { ...e, kind, a, b } as EdgePositioned;
      })
      .filter((x): x is EdgePositioned => x !== null);

    const nbr = new Map<string, Set<string>>();
    for (const e of edgesP) {
      if (!nbr.has(e.source)) nbr.set(e.source, new Set());
      if (!nbr.has(e.target)) nbr.set(e.target, new Set());
      nbr.get(e.source)!.add(e.target);
      nbr.get(e.target)!.add(e.source);
    }

    const byId = new Map<string, Positioned>();
    for (const n of [...actorPositions, ...dimPositions, ...signalTypePositions]) byId.set(n.id, n);

    return {
      actorNodes: actorPositions,
      dimNodes: dimPositions,
      signalTypeNodes: signalTypePositions,
      edges: edgesP,
      neighbours: nbr,
      nodeById: byId,
    };
  }, [graph]);

  if (!graph.nodes.length) return <div className="empty">No graph for this window.</div>;

  // Hovered node id (if any) — drives the dim-everything-else effect AND
  // the inspector contents when the user is hovering a node.
  const hoveredNodeId =
    inspect?.kind === "node" ? inspect.nodeId :
    inspect?.kind === "edge" ? null :
    null;

  const isActive = (id: string) => {
    if (!hoveredNodeId) return true;
    if (hoveredNodeId === id) return true;
    return neighbours.get(hoveredNodeId)?.has(id) ?? false;
  };
  const isEdgeActive = (e: EdgePositioned) => {
    if (inspect?.kind === "edge") {
      const idx = edges.indexOf(e);
      return idx === inspect.edgeIndex;
    }
    if (!hoveredNodeId) return true;
    return e.source === hoveredNodeId || e.target === hoveredNodeId;
  };

  // Bezier control point: push the midpoint outward from the centre.
  const edgePath = (e: EdgePositioned): string => {
    const mx = (e.a.x + e.b.x) / 2;
    const my = (e.a.y + e.b.y) / 2;
    const dx = mx - CX;
    const dy = my - CY;
    const len = Math.sqrt(dx * dx + dy * dy);
    const push = len > 0 ? 1.18 : 1;
    const cpx = CX + dx * push;
    const cpy = CY + dy * push;
    return `M ${e.a.x} ${e.a.y} Q ${cpx} ${cpy} ${e.b.x} ${e.b.y}`;
  };

  const tooltipForEdge = (e: EdgePositioned): string => {
    if (e.kind === "actor-actor") {
      const a = e.actor_a_label ?? e.source;
      const b = e.actor_b_label ?? e.target;
      const shared = e.shared?.join(", ") || `${e.weight} shared signal types`;
      return `${a} ↔ ${b}\nShared: ${shared}`;
    }
    if (e.kind === "actor-actor-sim") {
      const a = e.actor_a_label ?? e.source;
      const b = e.actor_b_label ?? e.target;
      const sim = e.similarity != null ? e.similarity.toFixed(3) : e.weight.toFixed(3);
      return `${a} ↔ ${b}\nSemantic similarity (centroid cosine): ${sim}`;
    }
    if (e.kind === "dim-signal-type") {
      return `${e.dimension_label ?? e.source} ∈ ${e.signal_type_label ?? e.target}`;
    }
    if (e.kind === "actor-signal-type") {
      const a = e.actor_label ?? e.source;
      const st = e.signal_type_label ?? e.target;
      return `${a} → ${st}\n${e.count ?? e.weight} signal${(e.count ?? e.weight) === 1 ? "" : "s"} aggregated`;
    }
    const a = e.actor_label ?? e.source;
    const d = e.dimension_label ?? e.target;
    const st = e.signal_type_label ? ` · ${e.signal_type_label}` : "";
    return `${a} → ${d}${st}\n${e.count ?? e.weight} signal${(e.count ?? e.weight) === 1 ? "" : "s"}`;
  };

  return (
    <div style={{ position: "relative" }}>
      <div
        style={{
          display: "flex",
          gap: "1.25rem",
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: "0.75rem",
          fontSize: "0.8rem",
          color: "var(--text-muted)",
        }}
      >
        <CategoryLegend nodes={actorNodes} />
        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={showPeerEdges}
            onChange={(e) => setShowPeerEdges(e.target.checked)}
          />
          <span>Show actor↔actor links ({edges.filter((e) => e.kind === "actor-actor").length})</span>
        </label>
        <span style={{ marginLeft: "auto", color: "var(--text-faint)" }}>
          Hover any node or edge to inspect
        </span>
      </div>

      <div style={{ position: "relative", width: "100%", overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: "100%", minWidth: 700, background: "var(--chart-bg)", borderRadius: 8 }}
          onMouseLeave={() => setInspect(null)}
        >
          {/* v0.4.40 — innermost ring only drawn when signal_type nodes are present. */}
          {signalTypeNodes.length > 0 && (
            <circle cx={CX} cy={CY} r={RING_SIGNAL_TYPE} fill="none" stroke="var(--ring-guide)" strokeDasharray="2 4" />
          )}
          <circle cx={CX} cy={CY} r={RING_DIM} fill="none" stroke="var(--ring-guide)" strokeDasharray="2 4" />
          <circle cx={CX} cy={CY} r={RING_ACTOR} fill="none" stroke="var(--ring-guide)" strokeDasharray="2 4" />

          {/* v0.4.40 — taxonomy backbone: dimension → signal_type. Always
              under the actor-dim layer so it stays visually subordinate. */}
          {edges
            .map((e, i) => ({ e, i }))
            .filter(({ e }) => e.kind === "dim-signal-type")
            .map(({ e, i }) => (
              <path
                key={`ds-${i}`}
                d={edgePath(e)}
                fill="none"
                stroke="var(--text-faint)"
                strokeWidth={1}
                strokeDasharray="3 3"
                opacity={isEdgeActive(e) ? 0.6 : 0.15}
                onMouseEnter={() => setInspect({ kind: "edge", edgeIndex: i })}
                style={{ cursor: "pointer" }}
              >
                <title>{tooltipForEdge(e)}</title>
              </path>
            ))}

          {/* v0.4.40 — semantic similarity overlay. Purple to distinguish
              from the actor-actor shared-dimension edges (blue-ish). */}
          {edges
            .map((e, i) => ({ e, i }))
            .filter(({ e }) => e.kind === "actor-actor-sim")
            .map(({ e, i }) => (
              <path
                key={`as-${i}`}
                d={edgePath(e)}
                fill="none"
                stroke="#a855f7"
                strokeWidth={Math.min(2.4, 0.6 + (e.similarity ?? e.weight) * 2.0)}
                strokeDasharray="5 4"
                opacity={isEdgeActive(e) ? 0.85 : 0.35}
                onMouseEnter={() => setInspect({ kind: "edge", edgeIndex: i })}
                style={{ cursor: "pointer" }}
              >
                <title>{tooltipForEdge(e)}</title>
              </path>
            ))}

          {showPeerEdges &&
            edges
              .map((e, i) => ({ e, i }))
              .filter(({ e }) => e.kind === "actor-actor")
              .map(({ e, i }) => (
                <path
                  key={`aa-${i}`}
                  d={edgePath(e)}
                  fill="none"
                  // Slightly wider invisible hit area for hover, then the
                  // visible coloured stroke.
                  stroke="#c7d2fe"
                  strokeWidth={Math.min(2.2, 0.4 + e.weight * 0.25)}
                  opacity={isEdgeActive(e) ? 0.55 : 0.04}
                  onMouseEnter={() => setInspect({ kind: "edge", edgeIndex: i })}
                  style={{ cursor: "pointer" }}
                >
                  <title>{tooltipForEdge(e)}</title>
                </path>
              ))}
          {edges
            .map((e, i) => ({ e, i }))
            .filter(({ e }) => e.kind === "actor-dim")
            .map(({ e, i }) => (
              <path
                key={`ad-${i}`}
                d={edgePath(e)}
                fill="none"
                stroke={inspect?.kind === "edge" && inspect.edgeIndex === i ? "#0f172a" : "#94a3b8"}
                strokeWidth={Math.min(3, 0.6 + Math.log2(e.weight + 1) * 0.6)}
                opacity={hoveredNodeId || inspect?.kind === "edge" ? (isEdgeActive(e) ? 0.9 : 0.05) : 0.4}
                onMouseEnter={() => setInspect({ kind: "edge", edgeIndex: i })}
                style={{ cursor: "pointer" }}
              >
                <title>{tooltipForEdge(e)}</title>
              </path>
            ))}

          {/* v0.4.40 — innermost signal_type nodes (4 Ehrenthal categories). */}
          {signalTypeNodes.map((s) => {
            const active = isActive(s.id);
            return (
              <g
                key={s.id}
                onMouseEnter={() => setInspect({ kind: "node", nodeId: s.id })}
                style={{ cursor: "pointer", opacity: active ? 1 : 0.25, transition: "opacity 120ms" }}
              >
                <circle cx={s.x} cy={s.y} r={11} fill={s.color} stroke="#fff" strokeWidth={2} />
                <LabelPill
                  x={s.x}
                  y={s.y + 22}
                  text={s.short_label || s.label}
                  fontSize={10}
                  fill="var(--text)"
                  anchor="middle"
                  weight={700}
                />
                <title>{s.label}</title>
              </g>
            );
          })}

          {dimNodes.map((d) => {
            const active = isActive(d.id);
            const lx = CX + (RING_DIM - 26) * Math.cos(d.angle);
            const ly = CY + (RING_DIM - 26) * Math.sin(d.angle);
            return (
              <g
                key={d.id}
                onMouseEnter={() => setInspect({ kind: "node", nodeId: d.id })}
                style={{ cursor: "pointer", opacity: active ? 1 : 0.18, transition: "opacity 120ms" }}
              >
                <circle cx={d.x} cy={d.y} r={9} fill={d.color} stroke="#fff" strokeWidth={1.5} />
                <LabelPill
                  x={lx}
                  y={ly}
                  text={d.label}
                  fontSize={11}
                  fill="var(--text)"
                  anchor="middle"
                  weight={600}
                />
                <title>
                  {d.label}
                  {d.signal_type_label ? ` · ${d.signal_type_label}` : ""}
                </title>
              </g>
            );
          })}

          {actorNodes.map((a) => {
            const active = isActive(a.id);
            const r = Math.min(15, 5 + (a.size || 12) / 3);
            const lx = CX + (RING_ACTOR + r + 6) * Math.cos(a.angle);
            const ly = CY + (RING_ACTOR + r + 6) * Math.sin(a.angle);
            const angDeg = (a.angle * 180) / Math.PI;
            const flip = a.angle > Math.PI / 2 || a.angle < -Math.PI / 2;
            const rotation = flip ? angDeg + 180 : angDeg;
            const anchor: "start" | "end" = flip ? "end" : "start";
            const label = a.label.length > 28 ? a.label.slice(0, 26) + "…" : a.label;

            return (
              <g
                key={a.id}
                onMouseEnter={() => setInspect({ kind: "node", nodeId: a.id })}
                style={{ cursor: "pointer", opacity: active ? 1 : 0.12, transition: "opacity 120ms" }}
              >
                <circle
                  cx={a.x}
                  cy={a.y}
                  r={r}
                  fill={a.color}
                  stroke="#fff"
                  strokeWidth={hoveredNodeId === a.id ? 3 : 1.5}
                />
                <text
                  x={lx}
                  y={ly}
                  fontSize={12}
                  fill="var(--text)"
                  textAnchor={anchor}
                  dominantBaseline="middle"
                  transform={`rotate(${rotation} ${lx} ${ly})`}
                  style={{ paintOrder: "stroke", stroke: "var(--chart-bg)", strokeWidth: 3, strokeLinejoin: "round" }}
                >
                  {label}
                </text>
                <title>
                  {a.label}
                  {a.category_label ? ` · ${a.category_label}` : ""}
                  {a.dimensions ? ` · covers ${a.dimensions} signal types` : ""}
                </title>
              </g>
            );
          })}
        </svg>

        <InspectorPanel
          inspect={inspect}
          edges={edges}
          nodeById={nodeById}
          neighbours={neighbours}
          onClose={() => setInspect(null)}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Inspector panel — describes whatever the user is currently hovering. */
/* ------------------------------------------------------------------ */

function InspectorPanel({
  inspect,
  edges,
  nodeById,
  neighbours,
  onClose,
}: {
  inspect: Inspect;
  edges: EdgePositioned[];
  nodeById: Map<string, Positioned>;
  neighbours: Map<string, Set<string>>;
  onClose: () => void;
}) {
  const baseStyle: React.CSSProperties = {
    position: "absolute",
    top: 16,
    right: 16,
    width: 320,
    maxHeight: 460,
    overflowY: "auto",
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "0.85rem 1rem",
    fontSize: "0.85rem",
    color: "var(--text)",
    boxShadow: "0 4px 16px rgba(15, 23, 41, 0.08)",
    pointerEvents: "none", // don't steal hover from the SVG underneath
  };

  if (!inspect) {
    return (
      <div style={{ ...baseStyle, color: "var(--text-faint)" }}>
        <strong style={{ color: "var(--text)" }}>Inspector</strong>
        <div style={{ marginTop: "0.5rem" }}>
          Hover an actor, a signal type, or an edge to see what it represents.
        </div>
      </div>
    );
  }

  if (inspect.kind === "node") {
    const node = nodeById.get(inspect.nodeId);
    if (!node) return null;
    // v0.4.40 — three node kinds now; signal_type is the new innermost one.
    const headerLabel =
      node.kind === "actor" ? "Actor" :
      node.kind === "signal_type" ? "Ehrenthal signal type" :
      "Dimension";
    return (
      <div style={baseStyle}>
        <Header onClose={onClose}>{headerLabel}</Header>
        <NodeBody node={node} edges={edges} nodeById={nodeById} neighbours={neighbours} />
      </div>
    );
  }

  // edge
  const e = edges[inspect.edgeIndex];
  if (!e) return null;
  // v0.4.40 — friendlier section headers for the new edge kinds.
  const edgeHeader =
    e.kind === "actor-actor" ? "Shared signal types" :
    e.kind === "actor-actor-sim" ? "Semantic similarity" :
    e.kind === "dim-signal-type" ? "Taxonomy edge" :
    e.kind === "actor-signal-type" ? "Aggregate volume" :
    "Edge";
  return (
    <div style={baseStyle}>
      <Header onClose={onClose}>{edgeHeader}</Header>
      <EdgeBody edge={e} />
    </div>
  );
}

function Header({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.5rem" }}>
      <strong style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--text-muted)" }}>
        {children}
      </strong>
      <button
        onClick={onClose}
        style={{
          pointerEvents: "auto",
          background: "transparent",
          border: "none",
          color: "var(--text-faint)",
          cursor: "pointer",
          fontSize: "0.85rem",
        }}
        title="Close"
      >
        ×
      </button>
    </div>
  );
}

function NodeBody({
  node,
  edges,
  nodeById,
  neighbours,
}: {
  node: Positioned;
  edges: EdgePositioned[];
  nodeById: Map<string, Positioned>;
  neighbours: Map<string, Set<string>>;
}) {
  if (node.kind === "actor") {
    // List the dimensions this actor touches with counts.
    const myEdges = edges.filter(
      (e) => e.kind === "actor-dim" && (e.source === node.id || e.target === node.id)
    );
    // Group by signal_type for readability.
    const byType = new Map<string, { label: string; entries: { label: string; count: number }[] }>();
    for (const e of myEdges) {
      const stLabel = e.signal_type_label || "Other";
      const stKey = e.signal_type || "other";
      const bucket = byType.get(stKey) || { label: stLabel, entries: [] };
      bucket.entries.push({ label: e.dimension_label || e.target, count: e.count ?? e.weight });
      byType.set(stKey, bucket);
    }
    return (
      <>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>{node.label}</div>
        <div style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          {node.category_label}
          {node.dimensions ? ` · covers ${node.dimensions} signal types` : ""}
        </div>
        {Array.from(byType.entries()).map(([stKey, group]) => (
          <div key={stKey} style={{ marginBottom: "0.6rem" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>{group.label}</div>
            {group.entries
              .sort((a, b) => b.count - a.count)
              .map((entry) => (
                <div key={entry.label} style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{entry.label}</span>
                  <span style={{ color: "var(--text-muted)" }}>{entry.count}</span>
                </div>
              ))}
          </div>
        ))}
      </>
    );
  }

  // v0.4.40 — signal_type node body: list the dimensions belonging
  // to this Ehrenthal category, plus the actors with the most volume
  // in it.
  if (node.kind === "signal_type") {
    const dimEdges = edges.filter(
      (e) => e.kind === "dim-signal-type" && (e.source === node.id || e.target === node.id),
    );
    const actorEdges = edges.filter(
      (e) => e.kind === "actor-signal-type" && (e.source === node.id || e.target === node.id),
    );
    return (
      <>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>{node.label}</div>
        <div style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Ehrenthal et al. 2026 four-signal scheme
        </div>
        {dimEdges.length > 0 && (
          <>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>
              Dimensions ({dimEdges.length})
            </div>
            {dimEdges
              .map((e) => {
                const dimId = e.source === node.id ? e.target : e.source;
                const dimNode = nodeById.get(dimId);
                return { label: dimNode?.label || e.dimension_label || dimId };
              })
              .map((entry) => (
                <div key={entry.label}>{entry.label}</div>
              ))}
          </>
        )}
        {actorEdges.length > 0 && (
          <>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.75rem", marginBottom: "0.3rem" }}>
              Actors by volume
            </div>
            {actorEdges
              .map((e) => {
                const actorId = e.source === node.id ? e.target : e.source;
                const actorNode = nodeById.get(actorId);
                return { label: actorNode?.label || e.actor_label || actorId, count: e.count ?? e.weight };
              })
              .sort((a, b) => b.count - a.count)
              .slice(0, 12)
              .map((entry) => (
                <div key={entry.label} style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>{entry.label}</span>
                  <span style={{ color: "var(--text-muted)" }}>{entry.count}</span>
                </div>
              ))}
          </>
        )}
      </>
    );
  }

  // Dimension node — list the actors that touch it.
  const myEdges = edges.filter(
    (e) => e.kind === "actor-dim" && (e.source === node.id || e.target === node.id)
  );
  return (
    <>
      <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>{node.label}</div>
      <div style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        {node.signal_type_label || ""}
        {node.cost_class ? ` · ${capitalise(node.cost_class)}-cost` : ""}
      </div>
      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.3rem" }}>
        {myEdges.length} actor{myEdges.length === 1 ? "" : "s"} emit this signal type
      </div>
      {myEdges
        .map((e) => {
          // Actor id is whichever side isn't us.
          const actorId = e.source === node.id ? e.target : e.source;
          const actorNode = nodeById.get(actorId);
          return { label: actorNode?.label || e.actor_label || actorId, count: e.count ?? e.weight };
        })
        .sort((a, b) => b.count - a.count)
        .map((entry) => (
          <div key={entry.label} style={{ display: "flex", justifyContent: "space-between" }}>
            <span>{entry.label}</span>
            <span style={{ color: "var(--text-muted)" }}>{entry.count}</span>
          </div>
        ))}
    </>
  );
}

function EdgeBody({ edge }: { edge: EdgePositioned }) {
  // v0.4.40 — semantic-similarity edge between two actors.
  if (edge.kind === "actor-actor-sim") {
    const sim = edge.similarity ?? edge.weight;
    return (
      <>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>
          {edge.actor_a_label ?? edge.source} ↔ {edge.actor_b_label ?? edge.target}
        </div>
        <div style={{ color: "var(--text-muted)", marginBottom: "0.6rem" }}>
          Centroid cosine similarity of pgvector embeddings (BGE-base-en-v1.5, 768d).
        </div>
        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
          Similarity
        </div>
        <div style={{ fontSize: "1.1rem", fontFamily: "var(--font-mono, monospace)" }}>
          {sim.toFixed(4)}
        </div>
      </>
    );
  }

  // v0.4.40 — taxonomy backbone edge: dimension belongs to signal_type.
  if (edge.kind === "dim-signal-type") {
    return (
      <>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>
          {edge.dimension_label ?? edge.source} ∈ {edge.signal_type_label ?? edge.target}
        </div>
        <div style={{ color: "var(--text-muted)" }}>
          The dimension belongs to this Ehrenthal signal type per `schema.yaml`.
        </div>
      </>
    );
  }

  // v0.4.40 — aggregated actor → signal_type volume.
  if (edge.kind === "actor-signal-type") {
    return (
      <>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>
          {edge.actor_label ?? edge.source} → {edge.signal_type_label ?? edge.target}
        </div>
        <div style={{ color: "var(--text-muted)" }}>
          {edge.count ?? edge.weight} signal{(edge.count ?? edge.weight) === 1 ? "" : "s"} aggregated across the four-signal scheme.
        </div>
      </>
    );
  }

  if (edge.kind === "actor-actor") {
    return (
      <>
        <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>
          {edge.actor_a_label ?? edge.source} ↔ {edge.actor_b_label ?? edge.target}
        </div>
        <div style={{ color: "var(--text-muted)", marginBottom: "0.6rem" }}>
          Sharing {edge.weight} signal type{edge.weight === 1 ? "" : "s"} in the same window.
        </div>
        {edge.shared_signal_types && edge.shared_signal_types.length > 0 && (
          <>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
              Shared Ehrenthal categories
            </div>
            <div style={{ marginBottom: "0.6rem" }}>{edge.shared_signal_types.join(" · ")}</div>
          </>
        )}
        {edge.shared && edge.shared.length > 0 && (
          <>
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
              Shared dimensions
            </div>
            <ul style={{ paddingLeft: "1.1rem", margin: 0 }}>
              {edge.shared.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </>
        )}
      </>
    );
  }

  return (
    <>
      <div style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "0.25rem" }}>
        {edge.actor_label ?? edge.source} → {edge.dimension_label ?? edge.target}
      </div>
      <div style={{ color: "var(--text-muted)", marginBottom: "0.6rem" }}>
        {edge.signal_type_label || "—"}
        {edge.cost_class ? ` · ${capitalise(edge.cost_class)}-cost signal` : ""}
        {" · "}
        {edge.count ?? edge.weight} signal{(edge.count ?? edge.weight) === 1 ? "" : "s"}
      </div>
      {edge.sample_titles && edge.sample_titles.length > 0 && (
        <>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
            Most recent
          </div>
          <ul style={{ paddingLeft: "1.1rem", margin: 0 }}>
            {edge.sample_titles.map((t) => (
              <li key={t} style={{ marginBottom: "0.2rem" }}>
                {t}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

function capitalise(s: string): string {
  if (!s) return s;
  return s[0].toUpperCase() + s.slice(1);
}

/**
 * Small inline category-colour legend strip. Builds itself from the
 * actor nodes present in the rendered graph so it never drifts from the
 * canvas's actual colour palette.
 */
function CategoryLegend({ nodes }: { nodes: Positioned[] }) {
  const seen = new Map<string, { label: string; color: string; count: number }>();
  for (const n of nodes) {
    const cat = n.category || "other";
    const label = n.category_label || cat;
    if (!seen.has(cat)) seen.set(cat, { label, color: n.color, count: 0 });
    seen.get(cat)!.count += 1;
  }
  const entries = Array.from(seen.entries()).sort(
    (a, b) =>
      CATEGORY_ORDER.indexOf(a[0]) - CATEGORY_ORDER.indexOf(b[0]) || a[1].label.localeCompare(b[1].label)
  );
  return (
    <div style={{ display: "flex", gap: "0.9rem", flexWrap: "wrap" }}>
      {entries.map(([cat, info]) => (
        <span key={cat} style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
          <span
            style={{
              display: "inline-block",
              width: 11,
              height: 11,
              borderRadius: "50%",
              background: info.color,
              border: "1px solid #fff",
              boxShadow: "0 0 0 1px #cbd5e1",
            }}
          />
          <span>{info.label} ({info.count})</span>
        </span>
      ))}
    </div>
  );
}

function LabelPill({
  x,
  y,
  text,
  fontSize = 11,
  fill = "var(--text)",
  anchor = "middle",
  weight = 400,
}: {
  x: number;
  y: number;
  text: string;
  fontSize?: number;
  fill?: string;
  anchor?: "start" | "middle" | "end";
  weight?: number;
}) {
  return (
    <text
      x={x}
      y={y}
      fontSize={fontSize}
      fill={fill}
      fontWeight={weight}
      textAnchor={anchor}
      dominantBaseline="middle"
      style={{ paintOrder: "stroke", stroke: "var(--chart-bg)", strokeWidth: 3, strokeLinejoin: "round" }}
    >
      {text}
    </text>
  );
}
