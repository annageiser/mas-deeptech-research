"use client";

import useSWR from "swr";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Card, PageHeader, CostBadge } from "@/components/ui";
import type { Signal } from "@/lib/types";

const fetcher = (u: string) => fetch(u).then((r) => r.json());

function SignalsInner() {
  const sp = useSearchParams();
  const system = sp.get("system") || "both";
  const days = sp.get("days") || "30";
  const [dimension, setDimension] = useState("");
  const [sourceKind, setSourceKind] = useState("");
  const [minConf, setMinConf] = useState(0);

  const q = new URLSearchParams();
  if (system !== "both") q.set("system", system);
  q.set("days", days);
  if (dimension) q.set("dimension", dimension);
  if (sourceKind) q.set("source_kind", sourceKind);
  if (minConf > 0) q.set("min_confidence", String(minConf));
  q.set("limit", "1000");

  const { data, isLoading } = useSWR<{ signals: Signal[]; count: number }>(`/api/signals?${q.toString()}`, fetcher);
  const rows = data?.signals || [];

  return (
    <>
      <Card style={{ marginBottom: "1rem" }}>
        <div className="filters" style={{ flexWrap: "wrap" }}>
          <select value={dimension} onChange={(e) => setDimension(e.target.value)}>
            <option value="">All signal types</option>
            {["technical_capability","research_output","ip_filing","infrastructure_or_facility","partnership_or_alliance","funding_or_grant","hiring_or_talent","regulatory_or_policy","market_positioning"].map((d) => (
              <option key={d} value={d}>{d.replace(/_/g, " ")}</option>
            ))}
          </select>
          <select value={sourceKind} onChange={(e) => setSourceKind(e.target.value)}>
            <option value="">All sources</option>
            <option value="arxiv">arXiv</option>
            <option value="website">Website</option>
            <option value="news">News</option>
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
                <th>When</th><th>Actor</th><th>Type</th><th>Cost</th><th>Headline</th><th className="num">Conf.</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td className="small faint">{(s.inserted_at || "").slice(0, 10)}</td>
                  <td className="small">{s.actor_name || s.actor_slug}</td>
                  <td className="small">{s.dimension_label}</td>
                  <td><CostBadge cost={s.cost_class || "medium"} /></td>
                  <td className="small">{s.title || s.summary?.slice(0, 80)}</td>
                  <td className="num">{Number(s.confidence).toFixed(2)}</td>
                  <td><a href={s.source_url} target="_blank" rel="noreferrer" className="small">↗</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
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
