import Link from "next/link";
import { GLOSSARY } from "@/lib/glossary";

/**
 * Inline term with a hover/focus tooltip explaining a metric or calculation.
 * Pure-CSS (no client JS) so it works in server components. `term` keys into
 * GLOSSARY; `children` is the visible text (defaults to the glossary title).
 * `align="end"` anchors the tooltip to the right edge — use it for the
 * right-most / numeric table columns so the bubble doesn't overflow the page.
 */
export function Term({
  term,
  children,
  align = "start",
}: {
  term: keyof typeof GLOSSARY | string;
  children?: React.ReactNode;
  align?: "start" | "end";
}) {
  const def = GLOSSARY[term as string];
  const label = children ?? def?.title ?? term;
  if (!def) return <>{label}</>;
  return (
    <span className={`term${align === "end" ? " term-end" : ""}`} tabIndex={0}>
      {label}
      <span className="tip" role="tooltip">
        <strong className="tip-title">{def.title}</strong>
        {def.formula && <code className="tip-formula">{def.formula}</code>}
        <span className="tip-body">{def.body}</span>
      </span>
    </span>
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <div className="card" style={style}>{children}</div>;
}

export function Stat({
  label,
  value,
  delta,
  deltaDir,
  help,
}: {
  label: string;
  value: React.ReactNode;
  delta?: string;
  deltaDir?: "up" | "down" | "flat";
  help?: string;
}) {
  return (
    <div className="card stat" title={help}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {delta && <div className={`delta ${deltaDir || "flat"}`}>{delta}</div>}
    </div>
  );
}

export function Bar({ value, max, color }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div className="bar">
      <span style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export function ChannelBadge({ channel }: { channel: string }) {
  const cap = channel === "capability";
  return <span className={`badge ${cap ? "cap" : "leg"}`}>{cap ? "Capability" : "Legitimacy"}</span>;
}

export function CostBadge({ cost }: { cost: string }) {
  const label = cost === "high" ? "High-cost" : cost === "low" ? "Cheap talk" : "Medium";
  return <span className={`badge cost-${cost}`}>{label}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="card empty">{children}</div>;
}

export function PageHeader({ title, lead }: { title: string; lead?: string }) {
  return (
    <div style={{ marginBottom: "1.25rem" }}>
      <h1>{title}</h1>
      {lead && <p className="muted" style={{ margin: 0, maxWidth: 760 }}>{lead}</p>}
    </div>
  );
}

export function ActorLink({ slug, name, system, days }: { slug: string; name: string; system?: string; days?: string }) {
  const q = new URLSearchParams();
  if (system && system !== "both") q.set("system", system);
  if (days && days !== "30") q.set("days", days);
  const s = q.toString();
  return <Link href={`/actors/${encodeURIComponent(slug)}${s ? `?${s}` : ""}`}>{name}</Link>;
}
