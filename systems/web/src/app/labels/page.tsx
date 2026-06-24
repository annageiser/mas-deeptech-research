"use client";

// v0.4.37 — Manual signal training page.
//
// Editorial layer: Anna inserts a URL + labels + notes + related actors,
// the API persists it to public.manual_signals, and both producer
// systems consume the entries as few-shot examples in their LLM prompts.
// A nightly sync also propagates each manual signal into public.signals
// as system='manual' so they appear on the regular /signals page and
// in /api/compare.
//
// Naming: the page lives at /labels (not /signals) to avoid clashing
// with the existing discovered-signals page. Nav label: "Label signals".

import useSWR, { mutate } from "swr";
import { useEffect, useMemo, useState } from "react";
import { Card, Empty, PageHeader } from "@/components/ui";
import type { Actor, ManualSignal } from "@/lib/types";

const fetcher = (u: string) => fetch(u).then((r) => r.json());

const SIGNAL_TYPES = [
  { key: "",                    label: "(unspecified)" },
  { key: "legitimacy",          label: "Legitimacy" },
  { key: "customer_cocreation", label: "Customer co-creation" },
  { key: "community_ecosystem", label: "Community / ecosystem" },
  { key: "future_trajectory",   label: "Future trajectory" },
];

interface FormState {
  source_url: string;
  title: string;
  notes: string;
  labels: string;       // comma-separated; split on submit
  signal_type: string;
  dimension: string;
  actor_slugs: string[];
}

const EMPTY_FORM: FormState = {
  source_url: "",
  title: "",
  notes: "",
  labels: "",
  signal_type: "",
  dimension: "",
  actor_slugs: [],
};

export default function LabelsPage() {
  const { data, error } = useSWR<{ manual_signals: ManualSignal[] }>(
    "/api/manual-signals?limit=500",
    fetcher,
  );
  const { data: actorsData } = useSWR<{ actors: Actor[] }>("/api/actors", fetcher);
  const rows = data?.manual_signals || [];
  const actors = actorsData?.actors || [];

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  function loadIntoForm(row: ManualSignal) {
    setEditingId(row.id);
    setForm({
      source_url: row.source_url,
      title: row.title || "",
      notes: row.notes || "",
      labels: (row.labels || []).join(", "),
      signal_type: row.signal_type || "",
      dimension: row.dimension || "",
      actor_slugs: row.actor_slugs || [],
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
      source_url: form.source_url.trim(),
      title: form.title.trim() || null,
      notes: form.notes.trim() || null,
      labels: form.labels.split(",").map((s) => s.trim()).filter(Boolean),
      signal_type: form.signal_type || null,
      dimension: form.dimension.trim() || null,
      actor_slugs: form.actor_slugs,
    };
    try {
      const url = editingId
        ? `/api/manual-signals/${editingId}`
        : "/api/manual-signals";
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
        await mutate("/api/manual-signals?limit=500");
      }
    } catch (e) {
      setErrorMsg((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this manual signal?")) return;
    const resp = await fetch(`/api/manual-signals/${id}`, { method: "DELETE" });
    if (resp.ok) {
      if (editingId === id) resetForm();
      await mutate("/api/manual-signals?limit=500");
    } else {
      setErrorMsg(`Delete failed (HTTP ${resp.status})`);
    }
  }

  return (
    <>
      <PageHeader
        title="Label signals"
        lead="Hand-curate signals (URL + labels + notes + related actors) so both producer systems can use them as few-shot examples and propagate them into the shared signals corpus as system='manual'."
      />

      <Card>
        <h3 style={{ marginTop: 0 }}>
          {editingId ? "Edit signal" : "Add a new signal"}
        </h3>
        <ManualSignalForm
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
        <h3 style={{ marginTop: 0 }}>
          All manually added signals ({rows.length})
        </h3>
        {error && <Empty>Failed to load manual signals.</Empty>}
        {!error && rows.length === 0 && <Empty>None yet. Add one above.</Empty>}
        {rows.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>URL / Title</th>
                <th>Signal type</th>
                <th>Labels</th>
                <th>Actors</th>
                <th>Updated</th>
                <th></th>
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

// ---------- form ----------

function ManualSignalForm({
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
          value={form.source_url}
          onChange={(e) => setForm({ ...form, source_url: e.target.value })}
          placeholder="https://example.org/article"
          style={inputStyle()}
          required
        />
      </Field>

      <Field label="Title (optional)">
        <input
          type="text"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          style={inputStyle()}
        />
      </Field>

      <Field label="Signal type">
        <select
          value={form.signal_type}
          onChange={(e) => setForm({ ...form, signal_type: e.target.value })}
          style={inputStyle()}
        >
          {SIGNAL_TYPES.map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>
      </Field>

      <Field label="Dimension (one of 19, e.g. funding_event, publications, …)">
        <input
          type="text"
          value={form.dimension}
          onChange={(e) => setForm({ ...form, dimension: e.target.value })}
          style={inputStyle()}
        />
      </Field>

      <Field label="Labels (comma-separated)">
        <input
          type="text"
          value={form.labels}
          onChange={(e) => setForm({ ...form, labels: e.target.value })}
          placeholder="grant, snf, eu, must-include"
          style={inputStyle()}
        />
      </Field>

      <Field label="Notes (free-form)">
        <textarea
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          rows={3}
          style={{ ...inputStyle(), fontFamily: "inherit" }}
        />
      </Field>

      <Field label={`Related actors (${form.actor_slugs.length} selected)`}>
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
          disabled={submitting || !form.source_url.trim()}
          style={btnStyle("primary")}
        >
          {submitting ? "Saving…" : editing ? "Save changes" : "Add signal"}
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
