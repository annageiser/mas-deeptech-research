import Link from "next/link";
import { notFound } from "next/navigation";
import { api } from "@/lib/api";
import { Card, PageHeader, Empty, ActorLink, Term } from "@/components/ui";
import { getPersona, PERSONA_LIST, METRICS } from "@/lib/personas";
import type { ActorScore, Insight } from "@/lib/types";

export const dynamic = "force-dynamic";

type SP = { params: { id: string }; searchParams: { system?: string; days?: string } };

/** Merge the active system/days context into a question deep-link. */
function withCtx(href: string, system: string, days: string): string {
  const [path, existing] = href.split("?");
  const q = new URLSearchParams(existing || "");
  if (system && system !== "both") q.set("system", system);
  if (days) q.set("days", days);
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}

export default async function PersonaPage({ params, searchParams }: SP) {
  const persona = getPersona(params.id);
  if (!persona) notFound();

  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");
  const daysStr = String(days);

  const [scoresRes, insightsRes] = await Promise.all([
    api.scores(system, days).catch(() => ({ scores: [] as ActorScore[] })),
    api.insights(persona.id, system, days).catch(() => ({ insights: [] as Insight[] } as any)),
  ]);
  const scores: ActorScore[] = scoresRes.scores || [];
  const insights: Insight[] = insightsRes.insights || [];

  const sortKey = persona.sortKey;
  const ranked = [...scores]
    .sort((a, b) => (Number(b[sortKey] ?? 0) - Number(a[sortKey] ?? 0)))
    .slice(0, 8);

  return (
    <>
      <PageHeader title={`${persona.icon} ${persona.label}`} lead={persona.tagline} />

      {/* persona switcher */}
      <div className="filters" style={{ marginBottom: "1rem", flexWrap: "wrap" }}>
        <span className="small muted">Lens:</span>
        <div className="seg">
          {PERSONA_LIST.map((p) => (
            <Link
              key={p.id}
              href={withCtx(`/personas/${p.id}`, system, daysStr)}
              className={p.id === persona.id ? "active" : ""}
              style={{ padding: "0.35rem 0.7rem", borderRadius: 6 }}
            >
              {p.icon} {p.label}
            </Link>
          ))}
        </div>
      </div>

      {/* framing */}
      <Card style={{ borderLeft: `3px solid ${persona.accent}` }}>
        <p style={{ margin: 0 }}>{persona.blurb}</p>
        {persona.caveat && (
          <p className="small muted" style={{ margin: "0.6rem 0 0" }}>⚠ {persona.caveat}</p>
        )}
      </Card>

      {/* what you can ask — deep links into existing pages with preset filters */}
      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>What you can ask</h3>
        <div className="grid cols-2">
          {persona.questions.map((qq) => (
            <Link
              key={qq.href}
              href={withCtx(qq.href, system, daysStr)}
              className="card"
              style={{ display: "block", textDecoration: "none", color: "inherit", padding: "0.7rem 0.9rem" }}
            >
              <span style={{ fontWeight: 600 }}>{qq.q}</span>
              <span className="small faint" style={{ display: "block", marginTop: 2 }}>Open →</span>
            </Link>
          ))}
        </div>
      </Card>

      {/* signals for you — descriptive insight cards */}
      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Signals for you</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Descriptive patterns over the current window — each with its source evidence. Correlational,
          not causal.
        </p>
        {insights.length ? (
          <div className="grid cols-2">
            {insights.slice(0, 8).map((ins) => (
              <div
                key={ins.id}
                className="card"
                style={{ borderLeft: `3px solid ${ins.severity === "watch" ? persona.accent : "var(--border)"}` }}
              >
                <div style={{ fontWeight: 600, marginBottom: 2 }}>{ins.title}</div>
                <div className="small muted">{ins.detail}</div>
                {ins.evidence?.length > 0 && (
                  <ul className="small" style={{ margin: "0.5rem 0 0", paddingLeft: "1.1rem" }}>
                    {ins.evidence.slice(0, 3).map((ev, i) => (
                      <li key={i} style={{ marginBottom: 2 }}>
                        {ev.source_url ? (
                          <a href={ev.source_url} target="_blank" rel="noreferrer">{ev.title || "source"}</a>
                        ) : (
                          <span>{ev.title}</span>
                        )}
                        {ev.dimension_label ? <span className="faint"> · {ev.dimension_label}</span> : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        ) : (
          <Empty>No insight patterns in this window. Widen the time window in the top-right.</Empty>
        )}
      </Card>

      {/* prioritised leaderboard for this lens */}
      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Ranked for this lens</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Top actors by <strong>{persona.sortLabel}</strong> — this lens's lead metric.
        </p>
        {ranked.length ? (
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Actor</th>
                <th>Category</th>
                {persona.metrics.map((k) => (
                  <th key={k} className="num">
                    <Term term={METRICS[k].glossaryKey} align="end">{METRICS[k].header}</Term>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ranked.map((a, i) => (
                <tr key={a.actor_slug}>
                  <td className="faint">{i + 1}</td>
                  <td><ActorLink slug={a.actor_slug} name={a.name || a.actor_slug} system={system} days={daysStr} /></td>
                  <td className="muted small">{a.category_label || "—"}</td>
                  {persona.metrics.map((k) => {
                    const spec = METRICS[k];
                    const v = Number(a[spec.field] ?? 0);
                    return <td key={k} className="num">{spec.fmt(v)}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>No signals in this window.</Empty>
        )}
        <p className="small faint" style={{ marginBottom: 0, marginTop: "0.6rem" }}>
          <Link href={withCtx("/leaderboard", system, daysStr)}>Full leaderboard →</Link>
        </p>
      </Card>

      <p className="small faint" style={{ marginTop: "1rem" }}>
        This lens re-orders and frames the same source-attributed signals — it derives no new data and makes
        no recommendation. See <Link href="/methodology">methodology</Link>.
      </p>
    </>
  );
}
