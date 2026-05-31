"use client";

import { useMemo, useState } from "react";
import type { KnowledgeGraph, KnowledgeGraphNode } from "@/lib/types";

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
 * This rewrite addresses each in turn:
 *
 *   - Outer-ring actors are sorted by category with small angular gaps
 *     between category groups, so the eye reads a colour wheel of
 *     (universities | private companies | initiatives | ecosystem builders).
 *   - Edges are quadratic Beziers whose control point is pushed *outward*
 *     from the centre, so they arc around the middle instead of crossing it.
 *   - Actor-actor edges are off by default (`showPeerEdges` toggle); they
 *     are the densest set and almost never inform a first read.
 *   - Outer-ring labels are rotated tangentially with a white background
 *     pill so they remain legible even when very close to a neighbour.
 *   - Hover an actor → that actor + its dimension neighbours light up,
 *     everything else fades to 12% opacity. Hover a dimension → all actors
 *     that touch it light up. This is the single highest-leverage
 *     readability win for a chart with this many crossings.
 *
 * Still dependency-free — same architectural choice as the rest of the site.
 */

type Positioned = KnowledgeGraphNode & {
  x: number;
  y: number;
  angle: number; // radians, used for tangential label rotation
};

type EdgePositioned = {
  source: string;
  target: string;
  kind: "actor-dim" | "actor-actor";
  weight: number;
  a: { x: number; y: number };
  b: { x: number; y: number };
};

// Geometry tuned for ~30 actors + ~9 dimensions; gracefully degrades for less.
const W = 1100;
const H = 800;
const CX = W / 2;
const CY = H / 2;
const RING_DIM = 200;
const RING_ACTOR = 330;
const CATEGORY_GAP_DEG = 6; // angular gap between category groups on the outer ring

// Category display order — choosing this fixes the colour wheel left-to-right
// so the legend reads naturally instead of in whatever insertion order Supabase
// returned.
const CATEGORY_ORDER = [
  "national_initiative",
  "university_or_research_hub",
  "private_company",
  "ecosystem_builder",
  "government",
];

export default function GraphCanvas({ graph }: { graph: KnowledgeGraph }) {
  const [hover, setHover] = useState<string | null>(null);
  const [showPeerEdges, setShowPeerEdges] = useState(false);

  const { actorNodes, dimNodes, allNodes, edges, neighbours } = useMemo(() => {
    const actorsRaw = graph.nodes.filter((n) => n.kind === "actor");
    const dimsRaw = graph.nodes.filter((n) => n.kind === "dimension");

    // 1) Sort actors so categories cluster on the outer ring. Categories
    //    in CATEGORY_ORDER first; anything unknown trails alphabetically.
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

    // 2) Place outer ring with angular gaps between category groups.
    //    Compute usable arc = 2π minus (#groups × gap), then distribute
    //    actor slots within each group's share proportional to count.
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

    let theta = -Math.PI / 2; // start at top
    const actorPositions: Positioned[] = [];
    let actorIdx = 0;
    for (const g of groupCounts) {
      for (let i = 0; i < g.count; i++) {
        // Centre each actor in its slot so the first/last of a group
        // don't kiss the gap edges.
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

    // 3) Dimensions equally spaced on the inner ring, starting at top.
    const dimPositions: Positioned[] = dimsRaw.map((d, i) => {
      const ang = (i / Math.max(1, dimsRaw.length)) * Math.PI * 2 - Math.PI / 2;
      return {
        ...d,
        x: CX + RING_DIM * Math.cos(ang),
        y: CY + RING_DIM * Math.sin(ang),
        angle: ang,
      };
    });

    const posMap = new Map<string, { x: number; y: number }>();
    for (const n of [...actorPositions, ...dimPositions]) posMap.set(n.id, { x: n.x, y: n.y });

    const edgesP: EdgePositioned[] = graph.edges
      .map((e) => {
        const a = posMap.get(e.source);
        const b = posMap.get(e.target);
        if (!a || !b) return null;
        // Narrow the wire-level `string` to the union the renderer expects.
        // Anything that isn't an actor-actor edge is treated as actor-dim
        // (the only two kinds the backend emits today; see knowledge_graph.py).
        const kind: EdgePositioned["kind"] = e.kind === "actor-actor" ? "actor-actor" : "actor-dim";
        return { source: e.source, target: e.target, kind, weight: e.weight, a, b };
      })
      .filter((x): x is EdgePositioned => x !== null);

    // Neighbour index for hover-highlighting (both directions for fast lookup).
    const nbr = new Map<string, Set<string>>();
    for (const e of edgesP) {
      if (!nbr.has(e.source)) nbr.set(e.source, new Set());
      if (!nbr.has(e.target)) nbr.set(e.target, new Set());
      nbr.get(e.source)!.add(e.target);
      nbr.get(e.target)!.add(e.source);
    }

    return {
      actorNodes: actorPositions,
      dimNodes: dimPositions,
      allNodes: [...dimPositions, ...actorPositions],
      edges: edgesP,
      neighbours: nbr,
    };
  }, [graph]);

  if (!graph.nodes.length) return <div className="empty">No graph for this window.</div>;

  // Hover dim: a node is "active" if it's the hovered node OR a direct
  // neighbour of it. When nothing is hovered, everything is fully visible.
  const isActive = (id: string) => {
    if (!hover) return true;
    if (hover === id) return true;
    return neighbours.get(hover)?.has(id) ?? false;
  };
  const isEdgeActive = (e: EdgePositioned) => {
    if (!hover) return true;
    return e.source === hover || e.target === hover;
  };

  // Bezier control point: push the midpoint outward from the centre so the
  // edge bows around the middle instead of cutting through it. The push
  // factor is tuned so the curves don't escape the actor ring.
  const edgePath = (e: EdgePositioned): string => {
    const mx = (e.a.x + e.b.x) / 2;
    const my = (e.a.y + e.b.y) / 2;
    const dx = mx - CX;
    const dy = my - CY;
    const len = Math.sqrt(dx * dx + dy * dy);
    const push = len > 0 ? 1.18 : 1; // 18% further from centre
    const cpx = CX + dx * push;
    const cpy = CY + dy * push;
    return `M ${e.a.x} ${e.a.y} Q ${cpx} ${cpy} ${e.b.x} ${e.b.y}`;
  };

  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: "1.25rem",
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: "0.75rem",
          fontSize: "0.8rem",
          color: "#5b6678",
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
        <span style={{ marginLeft: "auto", color: "#8892a6" }}>
          Hover any node to isolate its connections
        </span>
      </div>

      <div style={{ width: "100%", overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: "100%", minWidth: 700, background: "#fbfcfd", borderRadius: 8 }}
          onMouseLeave={() => setHover(null)}
        >
          {/* Ring guides — very faint, just for orientation */}
          <circle cx={CX} cy={CY} r={RING_DIM} fill="none" stroke="#eef0f4" strokeDasharray="2 4" />
          <circle cx={CX} cy={CY} r={RING_ACTOR} fill="none" stroke="#eef0f4" strokeDasharray="2 4" />

          {/* Edges. Actor-actor in background (always faint when on); actor-dim
              on top so they read as the primary information layer. */}
          {showPeerEdges &&
            edges
              .filter((e) => e.kind === "actor-actor")
              .map((e, i) => (
                <path
                  key={`aa-${i}`}
                  d={edgePath(e)}
                  fill="none"
                  stroke="#c7d2fe"
                  strokeWidth={Math.min(2.2, 0.4 + e.weight * 0.25)}
                  opacity={isEdgeActive(e) ? 0.45 : 0.04}
                />
              ))}
          {edges
            .filter((e) => e.kind === "actor-dim")
            .map((e, i) => (
              <path
                key={`ad-${i}`}
                d={edgePath(e)}
                fill="none"
                stroke="#94a3b8"
                strokeWidth={Math.min(2.5, 0.6 + Math.log2(e.weight + 1) * 0.6)}
                opacity={hover ? (isEdgeActive(e) ? 0.85 : 0.05) : 0.35}
              />
            ))}

          {/* Dimension nodes (inner ring) with labels just outside the ring,
              pointing toward the centre — keeps them away from actor labels. */}
          {dimNodes.map((d) => {
            const active = isActive(d.id);
            const lx = CX + (RING_DIM - 26) * Math.cos(d.angle);
            const ly = CY + (RING_DIM - 26) * Math.sin(d.angle);
            return (
              <g
                key={d.id}
                onMouseEnter={() => setHover(d.id)}
                style={{ cursor: "pointer", opacity: active ? 1 : 0.18, transition: "opacity 120ms" }}
              >
                <circle cx={d.x} cy={d.y} r={9} fill={d.color} stroke="#fff" strokeWidth={1.5} />
                <LabelPill
                  x={lx}
                  y={ly}
                  text={d.label}
                  fontSize={11}
                  fill="#0f1729"
                  anchor="middle"
                  weight={600}
                />
                <title>{d.label}</title>
              </g>
            );
          })}

          {/* Actor nodes (outer ring). Labels are tangential — rotated to the
              ring tangent and anchored outward, so neighbouring labels lie
              on radial lines instead of stacking horizontally. */}
          {actorNodes.map((a) => {
            const active = isActive(a.id);
            const r = Math.min(15, 5 + (a.size || 12) / 3);
            // Label position just outside the ring; rotate to match the
            // tangent so labels at the top point up, etc.
            const lx = CX + (RING_ACTOR + r + 6) * Math.cos(a.angle);
            const ly = CY + (RING_ACTOR + r + 6) * Math.sin(a.angle);
            // Convert angle to degrees. Flip labels on the left half so
            // they read left-to-right rather than upside down.
            const angDeg = (a.angle * 180) / Math.PI;
            const flip = a.angle > Math.PI / 2 || a.angle < -Math.PI / 2;
            const rotation = flip ? angDeg + 180 : angDeg;
            const anchor: "start" | "end" = flip ? "end" : "start";
            const label = a.label.length > 28 ? a.label.slice(0, 26) + "…" : a.label;

            return (
              <g
                key={a.id}
                onMouseEnter={() => setHover(a.id)}
                style={{ cursor: "pointer", opacity: active ? 1 : 0.12, transition: "opacity 120ms" }}
              >
                <circle
                  cx={a.x}
                  cy={a.y}
                  r={r}
                  fill={a.color}
                  stroke="#fff"
                  strokeWidth={hover === a.id ? 3 : 1.5}
                />
                <text
                  x={lx}
                  y={ly}
                  fontSize={12}
                  fill="#0f1729"
                  textAnchor={anchor}
                  dominantBaseline="middle"
                  transform={`rotate(${rotation} ${lx} ${ly})`}
                  style={{ paintOrder: "stroke", stroke: "#fbfcfd", strokeWidth: 3, strokeLinejoin: "round" }}
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
      </div>
    </div>
  );
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

/**
 * Text with a thicker semi-opaque stroke around it so the glyphs stay
 * readable even when they sit on top of edge lines or ring guides.
 * Uses SVG paint-order which is widely supported.
 */
function LabelPill({
  x,
  y,
  text,
  fontSize = 11,
  fill = "#0f1729",
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
      style={{ paintOrder: "stroke", stroke: "#fbfcfd", strokeWidth: 3, strokeLinejoin: "round" }}
    >
      {text}
    </text>
  );
}
