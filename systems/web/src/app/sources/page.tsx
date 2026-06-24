"use client";

// v0.4.37 — Source management page.
//
// CRUD over public.signal_sources: RSS / Atom / URL sources both
// producer systems consume in their daily cron. Replaces the
// (still-supported) data/raw/rss_feeds.yaml for DB-backed sources.
// Each source has: kind, optional label, optional per-source labels
// and related actors, enabled flag, and a crawl_frequency_hours
// hint that the producer cron treats as a floor (skip if
// last_fetched_at is newer than now() - crawl_frequency_hours).

import useSWR, { mutate } from "swr";
import { useMemo, useState } from "react";
import { Card, Empty, PageHeader } from "@/components/ui";
import type { Actor, SignalSource } from "@/lib/types";

const fetcher = (u: string) => fetch(u).then((r) => r.json());

const KINDS = [
  { key: "rss",  label: "RSS feed" },
  { key: "atom", label: "Atom feed" },
  { key: "url",  label: "Plain URL (page or one-off ingest)" },
];

interface FormState {
  url: string;
  kind: "rss" | "atom" | "url";
  label: string;
  notes: string;
  labels: string;        // comma-separated
  actor_slugs: string[];
  enabled: boolean;
  crawl_frequency_hours: number;
}

const EMPTY_FORM: FormState = {
  url: "",
  kind: "rss",
  label: "",
  notes: "",
  labels: "",
  actor_slugs: [],
  enabled: true,
  crawl_frequency_hours: 24,
};

export default function SourcesPage() {
  const { data, error } = useSWR<{ sources: SignalSource[] }>(
    "/api/sources?limit=500",
    fetcher,
  );
  const { data: actorsData } = useSWR<{ actors: Actor[] }>("/api/actors", fetcher);
  const rows = data?.sources || [];
  const actors = actorsData?.actors || [];

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function loadIntoForm(row: SignalSource) {
    setEditingId(row.id);
    setForm({
      url: row.url,
      kind: row.kind,
      label: row.label || "",
      notes: row.notes || "",
      labels: (row.labels || []).join(", "),
      actor_slugs: row.actor_slugs || [],
      enabled: row.enabled,
      crawl_frequency_hours: row.crawl_frequency_hours,
    });
    setErrorMsg(null);
  }

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setErrorMsg(null);
  }

  async function submit() {
    setSubmitting(true);
    setErrorMsg(null);
    const body = {
      url: form.url.trim(),
      kind: form.kind,
      label: form.label.trim() || null,
      notes: form.notes.trim() || null,
      labels: form.labels.split(",").map((s) => s.trim()).filter(Boolean),
      actor_slugs: form.actor_slugs,
      enabled: form.enabled,
      crawl_frequency_hours: form.crawl_frequency_hours,
    };
    try {
      const url = editingId ? `/api/sources/${editingId}` : "/api/sources";
      const method = editingId ? "PATCH" : "POST";
      const resp = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        setErrorMsg(payload.detail || `HTTP ${resp.status}`);
      } else {
        resetForm();
        await mutate("/api/sources?limit=500");
      }
    } catch (e) {
      setErrorMsg((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this source?")) return;
    const resp = await fetch(`/api/sources/${id}`, { method: "DELETE" });
    if (resp.ok) {
      if (editingId === id) resetForm();
      await mutate("/api/sources?limit=500");
    } else {
      setErrorMsg(`Delete failed (HTTP ${resp.status})`);
    }
  }

  async function toggleEnabled(row: SignalSource) {
    const resp = await fetch(`/api/sources/${row.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !row.enabled }),
    });
    if (resp.ok) await mutate("/api/sources?limit=500");
  }

  return (
    <>
      <PageHeader
        title="Sources"
        lead="RSS / Atom / URL sources both producer systems consume daily. Per-source enable, crawl frequency, label and actor attachments. Replaces the static data/raw/rss_feeds.yaml for DB-managed sources."
      />

      <Card>
        <h3 style={{ marginTop: 0 }}>
          {editingId ? "Edit source" : "Add a new source"}
        </h3>
        <SourceForm
          form={form}
          setForm={setForm}
          actors={actors}
          submitting={submitting}
          editing={!!editingId}
          onSubmit={submit}
          onReset={resetForm}
        />
        {errorMsg && (
          <div className="small" style={{ color: "var(--danger, #dc2626)", marginTop: "0.5rem" }}>
            {errorMsg}
          </div>
        )}
      </Card>

      <div style={{ height: "1rem" }} />

      <Card>
        <h3 style={{ marginTop: 0 }}>All sources ({rows.length})</h3>
        {error && <Empty>Failed to load sources.</Empty>}
        {!error && rows.length === 0 && <Empty>None yet. Add one above.</Empty>}
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
                <th></th>
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
                  <td className="small">
                    <button type="button" onClick={() => toggleEnabled(r)}
                            style={btnStyle(r.enabled ? "primary" : "")}>
                      {r.enabled ? "on" : "off"}
                    </button>
                  </td>
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
                  <td className="small" style={{ whiteSpace: "nowrap" }}>
                    <button type="button" onClick={() => loadIntoForm(r)}
                            style={btnStyle()}>Edit</button>
                    {" "}
                    <button type="button" onClick={() => remove(r.id)}
                            style={btnStyle("danger")}>Delete</button>
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

function SourceForm({
  form, setForm, actors, submitting, editing, onSubmit, onReset,
}: {
  form: FormState;
  setForm: (f: FormState) => void;
  actors: Actor[];
  submitting: boolean;
  editing: boolean;
  onSubmit: () => void;
  onReset: () => void;
}) {
  const sortedActors = useMemo(
    () => [...actors].sort((a, b) => a.name.localeCompare(b.name)),
    [actors],
  );

  function toggleActor(slug: string) {
    if (form.actor_slugs.includes(slug)) {
      setForm({ ...form, actor_slugs: form.actor_slugs.filter((s) => s !== slug) });
    } else {
      setForm({ ...form, actor_slugs: [...form.actor_slugs, slug] });
    }
  }

  return (
    <div style={{ display: "grid", gap: "0.6rem" }}>
      <Field label="Source URL *">
        <input
          type="url"
          value={form.url}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
          placeholder="https://example.org/feed.xml"
          style={inputStyle()}
          required
        />
      </Field>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.6rem" }}>
        <Field label="Kind *">
          <select
            value={form.kind}
            onChange={(e) => setForm({ ...form, kind: e.target.value as FormState["kind"] })}
            style={inputStyle()}
          >
            {KINDS.map((k) => (
              <option key={k.key} value={k.key}>{k.label}</option>
            ))}
          </select>
        </Field>

        <Field label="Enabled">
          <select
            value={form.enabled ? "1" : "0"}
            onChange={(e) => setForm({ ...form, enabled: e.target.value === "1" })}
            style={inputStyle()}
          >
            <option value="1">Yes</option>
            <option value="0">No</option>
          </select>
        </Field>

        <Field label="Crawl every (hours)">
          <input
            type="number"
            min={0}
            max={720}
            value={form.crawl_frequency_hours}
            onChange={(e) => setForm({ ...form, crawl_frequency_hours: parseInt(e.target.value || "24", 10) })}
            style={inputStyle()}
          />
        </Field>
      </div>

      <Field label="Label (human-readable name)">
        <input
          type="text"
          value={form.label}
          onChange={(e) => setForm({ ...form, label: e.target.value })}
          placeholder="ETH Research Collection — quantum atom feed"
          style={inputStyle()}
        />
      </Field>

      <Field label="Labels (comma-separated)">
        <input
          type="text"
          value={form.labels}
          onChange={(e) => setForm({ ...form, labels: e.target.value })}
          placeholder="academic, atom, quantum"
          style={inputStyle()}
        />
      </Field>

      <Field label="Notes (free-form)">
        <textarea
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          rows={2}
          style={{ ...inputStyle(), fontFamily: "inherit" }}
        />
      </Field>

      <Field label={`Related actors (${form.actor_slugs.length} selected — leave empty to apply to all)`}>
        <div
          style={{
            maxHeight: 180,
            overflow: "auto",
            border: "1px solid var(--border)",
            borderRadius: 4,
            padding: "0.4rem",
            fontSize: "0.85rem",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "0.2rem 0.6rem",
          }}
        >
          {sortedActors.map((a) => (
            <label key={a.slug} style={{ display: "flex", gap: "0.3rem", alignItems: "center", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={form.actor_slugs.includes(a.slug)}
                onChange={() => toggleActor(a.slug)}
              />
              <span>{a.name}</span>
            </label>
          ))}
        </div>
      </Field>

      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.3rem" }}>
        <button
          type="button"
          onClick={onSubmit}
          disabled={submitting || !form.url.trim()}
          style={btnStyle("primary")}
        >
          {submitting ? "Saving…" : editing ? "Save changes" : "Add source"}
        </button>
        {editing && (
          <button type="button" onClick={onReset} style={btnStyle()}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block" }}>
      <div className="small faint" style={{ marginBottom: 2 }}>{label}</div>
      {children}
    </label>
  );
}

function inputStyle(): React.CSSProperties {
  return {
    width: "100%",
    padding: "0.35rem 0.5rem",
    border: "1px solid var(--border)",
    borderRadius: 4,
    background: "var(--surface)",
    color: "var(--text)",
    fontSize: "0.9rem",
  };
}

function btnStyle(variant: "primary" | "danger" | "" = ""): React.CSSProperties {
  const base: React.CSSProperties = {
    padding: "0.3rem 0.7rem",
    border: "1px solid var(--border)",
    borderRadius: 4,
    background: "var(--surface)",
    color: "var(--text)",
    cursor: "pointer",
    fontSize: "0.85rem",
  };
  if (variant === "primary") {
    return { ...base, background: "var(--brand, #2563eb)", color: "#fff", borderColor: "transparent" };
  }
  if (variant === "danger") {
    return { ...base, background: "transparent", color: "var(--danger, #dc2626)", borderColor: "var(--danger, #dc2626)" };
  }
  return base;
}
