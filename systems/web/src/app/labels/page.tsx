"use client";

// Post-thesis (v0.5.6): read-only view of manually curated signals.
// Editorial CRUD (create / edit / delete) was removed when the project
// shipped; the page now displays the frozen manual_signals table only.

import useSWR from "swr";
import { Card, Empty, PageHeader } from "@/components/ui";
import type { ManualSignal } from "@/lib/types";

const fetcher = (u: string) => fetch(u).then((r) => r.json());

export default function LabelsPage() {
  const { data, error } = useSWR<{ manual_signals: ManualSignal[] }>(
    "/api/manual-signals?limit=500",
    fetcher,
  );
  const rows = data?.manual_signals || [];

  return (
    <>
      <PageHeader
        title="Manually curated signals"
        lead="Hand-labelled signals that were fed to both producer systems as few-shot examples and propagated into the shared corpus as system='manual'."
      />

      <Card>
        <h3 style={{ marginTop: 0 }}>
          Manually added signals ({rows.length})
        </h3>
        {error && <Empty>Failed to load manual signals.</Empty>}
        {!error && rows.length === 0 && <Empty>None recorded.</Empty>}
        {rows.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>URL / Title</th>
                <th>Signal type</th>
                <th>Labels</th>
                <th>Actors</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td style={{ maxWidth: 380 }}>
                    <a href={r.source_url} target="_blank" rel="noreferrer" className="muted">
                      {r.title || r.source_url}
                    </a>
                    {r.notes && (
                      <div className="small faint" style={{ marginTop: 2 }}>
                        {r.notes.length > 140 ? r.notes.slice(0, 140) + "…" : r.notes}
                      </div>
                    )}
                  </td>
                  <td className="small">{r.signal_type || "—"}</td>
                  <td className="small">{(r.labels || []).join(", ") || "—"}</td>
                  <td className="small">{(r.actor_slugs || []).join(", ") || "—"}</td>
                  <td className="small faint">
                    {new Date(r.updated_at).toISOString().slice(0, 10)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
