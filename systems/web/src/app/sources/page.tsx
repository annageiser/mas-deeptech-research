"use client";

// Post-thesis (v0.5.6): read-only view of signal_sources. Add / edit /
// delete / toggle-enabled UI was removed when the project shipped; the
// page now displays the frozen source list only.

import useSWR from "swr";
import { Card, Empty, PageHeader } from "@/components/ui";
import type { SignalSource } from "@/lib/types";

const fetcher = (u: string) => fetch(u).then((r) => r.json());

export default function SourcesPage() {
  const { data, error } = useSWR<{ sources: SignalSource[] }>(
    "/api/sources?limit=500",
    fetcher,
  );
  const rows = data?.sources || [];

  return (
    <>
      <PageHeader
        title="Sources"
        lead="RSS / Atom / URL sources both producer systems consumed daily during the collection phase."
      />

      <Card>
        <h3 style={{ marginTop: 0 }}>All sources ({rows.length})</h3>
        {error && <Empty>Failed to load sources.</Empty>}
        {!error && rows.length === 0 && <Empty>None recorded.</Empty>}
        {rows.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>URL / Label</th>
                <th>Kind</th>
                <th>Enabled</th>
                <th>Every</th>
                <th>Last fetched</th>
                <th>Last status</th>
                <th>Actors</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} style={{ opacity: r.enabled ? 1 : 0.6 }}>
                  <td style={{ maxWidth: 320 }}>
                    <a href={r.url} target="_blank" rel="noreferrer" className="muted">
                      {r.label || r.url}
                    </a>
                    {r.label && (
                      <div className="small faint" style={{ marginTop: 2 }}>{r.url}</div>
                    )}
                  </td>
                  <td className="small">{r.kind.toUpperCase()}</td>
                  <td className="small">{r.enabled ? "on" : "off"}</td>
                  <td className="small">{r.crawl_frequency_hours}h</td>
                  <td className="small faint">
                    {r.last_fetched_at
                      ? new Date(r.last_fetched_at).toISOString().replace("T", " ").slice(0, 16)
                      : "—"}
                  </td>
                  <td className="small">
                    {r.last_status === "ok"
                      ? `ok (${r.last_item_count})`
                      : r.last_status === "error"
                      ? <span style={{ color: "var(--danger, #dc2626)" }}>error</span>
                      : "—"}
                  </td>
                  <td className="small">{(r.actor_slugs || []).join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
