"use client";

import useSWR from "swr";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Card, PageHeader, CostBadge } from "@/components/ui";
import type { Signal } from "@/lib/types";

const fetcher = (u: string) => fetch(u).then((r) => r.json());

// Ehrenthal four-signal scheme — top-level filter axis. The 19 dimensions
// are grouped under these four when the user wants to drill down.
const SIGNAL_TYPES = [
  { key: "legitimacy",          label: "Legitimacy",          color: "#1f77b4" },
  { key: "customer_cocreation", label: "Customer co-creation", color: "#2ca02c" },
  { key: "community_ecosystem", label: "Community / ecosystem", color: "#9467bd" },
  { key: "future_trajectory",   label: "Future trajectory",    color: "#ff7f0e" },
];

const DIMENSIONS_BY_SIGNAL_TYPE: Record<string, { key: string; label: string }[]> = {
  legitimacy: [
    { key: "leadership_expertise",   label: "Leadership / board expertise" },
    { key: "patents",                label: "Patents" },
    { key: "publications",           label: "Publications" },
    { key: "awards",                 label: "Awards" },
    { key: "testimonials",           label: "Testimonials" },
    { key: "educational_outreach",   label: "Educational outreach" },
    { key: "funding_event",          label: "Funding event" },
    { key: "regulatory_recognition", label: "Regulatory recognition" },
  ],
  customer_cocreation: [
    { key: "collaborations_applications", label: "Collaborations for applications" },
    { key: "pilots_pocs",                 label: "Pilots & POCs" },
    { key: "customer_training",           label: "Customer training" },
  ],
  community_ecosystem: [
    { key: "cloud_platform_listings", label: "Cloud-platform listings" },
    { key: "hpc_collaborations",      label: "HPC collaborations" },
    { key: "industry_partnerships",   label: "Industry partnerships" },
    { key: "academic_partnerships",   label: "Academic partnerships" },
  ],
  future_trajectory: [
    { key: "roadmaps",               label: "Roadmaps" },
    { key: "milestones",             label: "Milestones" },
    { key: "technological_advances", label: "Technological advances" },
    { key: "long_horizon_claims",    label: "Long-horizon claims" },
  ],
};

function SignalsInner() {
  const sp = useSearchParams();
  const system = sp.get("system") || "both";
  const days = sp.get("days") || "90";
  const [signalType, setSignalType] = useState(sp.get("signal_type") || "");
  const [dimension, setDimension] = useState(sp.get("dimension") || "");
  const [sourceKind, setSourceKind] = useState("");
  const [minConf, setMinConf] = useState(0);

  // Sub-dimension options react to the selected signal_type. If you pick a
  // signal_type and then a dimension that isn't under it, we silently clear
  // the dimension on the next render to avoid an empty result-set.
  const dimensionOptions = signalType
    ? DIMENSIONS_BY_SIGNAL_TYPE[signalType] || []
    : Object.values(DIMENSIONS_BY_SIGNAL_TYPE).flat();
  const dimensionIsValid =
    !dimension || dimensionOptions.some((o) => o.key === dimension);

  const q = new URLSearchParams();
  if (system !== "both") q.set("system", system);
  q.set("days", days);
  if (signalType) q.set("signal_type", signalType);
  if (dimension && dimensionIsValid) q.set("dimension", dimension);
  if (sourceKind) q.set("source_kind", sourceKind);
  if (minConf > 0) q.set("min_confidence", String(minConf));
  q.set("limit", "1000");

  const { data, isLoading } = useSWR<{ signals: Signal[]; count: number }>(`/api/signals?${q.toString()}`, fetcher);
  const rows = data?.signals || [];

  return (
    <>
      <Card style={{ marginBottom: "1rem" }}>
        <div className="filters" style={{ flexWrap: "wrap" }}>
          {/* PRIMARY filter (v0.4.0): Ehrenthal four-signal scheme */}
          <label className="small muted" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
            <strong>Signal type</strong>
            <select
              value={signalType}
              onChange={(e) => {
                setSignalType(e.target.value);
                setDimension(""); // reset sub-dimension when the parent changes
              }}
            >
              <option value="">All four</option>
              {SIGNAL_TYPES.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </select>
          </label>

          {/* SECONDARY filter: sub-dimension (filtered to the chosen signal_type) */}
          <label className="small muted" style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
            Sub-dimension
            <select value={dimensionIsValid ? dimension : ""} onChange={(e) => setDimension(e.target.value)}>
              <option value="">
                {signalType ? `All ${dimensionOptions.length} under ${SIGNAL_TYPES.find(t => t.key === signalType)?.label}` : "All 19 sub-dimensions"}
              </option>
              {dimensionOptions.map((d) => (
                <option key={d.key} value={d.key}>{d.label}</option>
              ))}
            </select>
          </label>

          <select value={sourceKind} onChange={(e) => setSourceKind(e.target.value)}>
            <option value="">All sources</option>
            <option value="arxiv">arXiv</option>
            <option value="website">Website</option>
            <option value="news">News</option>
            <option value="swissreg">Patents</option>
          </select>
          <label className="small muted">
            Min confidence {minConf.toFixed(2)}{" "}
            <input type="range" min={0} max={1} step={0.05} value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} />
          </label>
          <span className="small faint">{rows.length} shown</span>
        </div>
      </Card>

      {isLoading ? (
        <div className="empty">Loading…</div>
      ) : (
        <Card>
          <table>
            <thead>
              <tr>
                <th>When</th><th>Actor</th><th>Signal type</th><th>Sub-dimension</th><th>Cost</th><th>Sent.</th><th>Headline</th><th className="num">Conf.</th><th></th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td className="small faint">{(s.inserted_at || "").slice(0, 10)}</td>
                  <td className="small">{s.actor_name || s.actor_slug}</td>
                  <td className="small">
                    {s.signal_type_label ? (
                      <span style={{
                        display: "inline-block",
                        padding: "0.05rem 0.35rem",
                        borderRadius: 3,
                        fontSize: "0.7rem",
                        background: SIGNAL_TYPES.find(t => t.key === s.signal_type)?.color || "#888",
                        color: "#fff",
                      }}>
                        {SIGNAL_TYPES.find(t => t.key === s.signal_type)?.label || s.signal_type}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="small">{s.dimension_label}</td>
                  <td><CostBadge cost={s.cost_class || "medium"} /></td>
                  <td><SentimentBadge label={s.sentiment_label ?? null} score={s.sentiment_score ?? null} /></td>
                  <td className="small">{s.title || s.summary?.slice(0, 80)}</td>
                  <td className="num">{Number(s.confidence).toFixed(2)}</td>
                  <td><a href={s.source_url} target="_blank" rel="noreferrer" className="small">↗</a></td>
                  <td><FlagButton signalId={s.id} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// SentimentBadge — v0.4.24. Small coloured chip on each row showing the VADER
// sentiment label for the signal's evidence + summary. Hovered tooltip shows
// the compound score. Renders an em-dash for legacy rows (sentiment NULL).
// ---------------------------------------------------------------------------

const SENTIMENT_STYLES: Record<string, { bg: string; fg: string; symbol: string }> = {
  positive: { bg: "#dcfce7", fg: "#166534", symbol: "+" },
  neutral:  { bg: "#f1f5f9", fg: "#475569", symbol: "·" },
  negative: { bg: "#fee2e2", fg: "#991b1b", symbol: "−" },
};

function SentimentBadge({ label, score }: { label: string | null; score: number | null }) {
  if (!label) return <span className="small faint">—</span>;
  const style = SENTIMENT_STYLES[label] || SENTIMENT_STYLES.neutral;
  const tooltip = score != null ? `VADER compound ${score.toFixed(2)}` : `VADER label: ${label}`;
  return (
    <span
      className="small"
      title={tooltip}
      style={{
        display: "inline-block",
        padding: "0.05rem 0.35rem",
        borderRadius: 3,
        background: style.bg,
        color: style.fg,
        fontSize: "0.7rem",
        fontWeight: 600,
      }}
    >
      {style.symbol}
    </span>
  );
}

// ---------------------------------------------------------------------------
// FlagButton — quick wrong-signal-report UI. Hits POST /api/signal-flags
// (Workflow B from docs/wrong-signals-strategy.md). Six reason buckets;
// once flagged, the row's button locks to a "Flagged" pill.
// ---------------------------------------------------------------------------

const FLAG_REASONS: { key: string; label: string; positive?: boolean }[] = [
  // v0.4.2: positive label — Anna marks a signal as a gold example
  { key: "correct_example", label: "Mark as correct example (teach the system)", positive: true },
  // ---- separator ----
  { key: "wrong_actor",     label: "Wrong actor" },
  { key: "off_topic",       label: "Not about quantum" },
  { key: "wrong_dimension", label: "Wrong dimension" },
  { key: "low_quality",     label: "Boilerplate / no substance" },
  { key: "duplicate",       label: "Duplicate of another signal" },
  { key: "other",           label: "Other" },
];

function FlagButton({ signalId }: { signalId: string }) {
  const [open, setOpen] = useState(false);
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function flag(reason: string) {
    setPending(true);
    try {
      const resp = await fetch("/api/signal-flags", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ signal_id: signalId, reason }),
      });
      if (resp.ok) {
        setSubmitted(reason);
      }
    } catch {
      // soft-fail: button stays clickable
    } finally {
      setPending(false);
      setOpen(false);
    }
  }

  if (submitted) {
    return (
      <span
        className="small"
        style={{
          display: "inline-block",
          padding: "0.05rem 0.4rem",
          borderRadius: 3,
          background: "var(--badge-low-bg)",
          color: "var(--badge-low-fg)",
          fontSize: "0.7rem",
        }}
        title={`Flagged: ${submitted}`}
      >
        Flagged
      </span>
    );
  }

  return (
    <span style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        disabled={pending}
        title="Report this signal as wrong"
        style={{
          background: "transparent",
          border: "1px solid var(--border)",
          borderRadius: 3,
          padding: "0.05rem 0.35rem",
          fontSize: "0.7rem",
          color: "var(--text-muted)",
          cursor: "pointer",
        }}
      >
        Flag
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "100%",
            marginTop: 4,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            boxShadow: "var(--shadow-lg)",
            padding: "0.4rem 0.5rem",
            zIndex: 20,
            minWidth: 200,
          }}
        >
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: 4 }}>
            Why is it wrong?
          </div>
          {FLAG_REASONS.map((r) => (
            <button
              key={r.key}
              type="button"
              onClick={() => flag(r.key)}
              disabled={pending}
              style={{
                display: "block",
                width: "100%",
                textAlign: "left",
                background: "transparent",
                border: "none",
                padding: "0.3rem 0.4rem",
                borderRadius: 4,
                fontSize: "0.8rem",
                color: "var(--text)",
                cursor: pending ? "default" : "pointer",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "var(--surface-2)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
            >
              {r.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}

export default function SignalsPage() {
  return (
    <>
      <PageHeader title="Signals" lead="Every signal in the window, filterable. The raw evidence behind every score — each row links to its source." />
      <Suspense fallback={<div className="empty">Loading…</div>}>
        <SignalsInner />
      </Suspense>
    </>
  );
}
