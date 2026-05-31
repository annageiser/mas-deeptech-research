"use client";

import useSWR from "swr";
import { useState } from "react";
import { Card, PageHeader } from "@/components/ui";
import Markdown from "@/components/Markdown";
import type { ReportListItem } from "@/lib/types";

const fetcher = (u: string) => fetch(u).then((r) => r.json());

export default function ReportsPage() {
  const { data } = useSWR<{ reports: ReportListItem[] }>("/api/reports", fetcher);
  const reports = data?.reports || [];
  const [sel, setSel] = useState<ReportListItem | null>(null);

  const active = sel || reports[0] || null;
  const key = active ? `/api/reports?kind=${active.kind}&period=${active.period}&file=${active.file}` : null;
  const { data: body } = useSWR<{ markdown: string }>(key, fetcher);

  const kinds: Record<string, string> = { daily: "Daily", weekly: "Weekly (per system)", thesis: "Thesis progress" };

  return (
    <>
      <PageHeader title="Reports" lead="Auto-generated narrative briefings — daily per system, weekly summaries, and a weekly thesis-progress report." />
      <div className="grid" style={{ gridTemplateColumns: "300px 1fr", gap: "1rem", alignItems: "start" }}>
        <Card>
          {["thesis", "weekly", "daily"].map((k) => {
            const items = reports.filter((r) => r.kind === k);
            if (!items.length) return null;
            return (
              <div key={k} style={{ marginBottom: "1rem" }}>
                <div className="nav-group-label" style={{ padding: "0 0 0.3rem" }}>{kinds[k] || k}</div>
                {items.slice(0, 20).map((r) => (
                  <div
                    key={`${r.kind}/${r.period}/${r.file}`}
                    onClick={() => setSel(r)}
                    className="nav-link"
                    style={{ cursor: "pointer", background: active && active.file === r.file && active.period === r.period ? "var(--brand-soft)" : undefined }}
                  >
                    <span className="small">{r.title}</span>
                  </div>
                ))}
              </div>
            );
          })}
          {!reports.length && <div className="empty small">No reports yet. They appear after the first daily/weekly cron run.</div>}
        </Card>
        <Card>
          {active ? (
            body?.markdown ? <Markdown source={body.markdown} /> : <div className="empty">Loading…</div>
          ) : (
            <div className="empty">Select a report.</div>
          )}
        </Card>
      </div>
    </>
  );
}
