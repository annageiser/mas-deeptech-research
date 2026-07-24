import { api } from "@/lib/api";
import { Card, Stat, Empty, PageHeader, ChannelBadge, CostBadge } from "@/components/ui";
import { HBar } from "@/components/charts";

export const dynamic = "force-dynamic";

type SP = { params: { slug: string }; searchParams: { system?: string; days?: string } };

export default async function ActorDetail({ params, searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");

  let data;
  try {
    data = await api.actor(params.slug, system, days);
  } catch (e: any) {
    return <Empty>Actor not found, or the data API is unreachable.</Empty>;
  }

  const a = data.actor;
  const sc = data.score;
  const mix = (data.signal_mix || []).map((m: any) => ({ label: m.label, count: m.count }));

  return (
    <>
      <PageHeader title={a.name} lead={a.category_label || undefined} />

      <div className="pill-row" style={{ marginBottom: "1rem" }}>
        {a.homepage && <a className="badge cap" href={a.homepage} target="_blank" rel="noreferrer">Homepage ↗</a>}
        {data.rank_in_category && (
          <span className="badge leg">Rank #{data.rank_in_category} of {data.peers_in_category} in category</span>
        )}
      </div>

      {sc ? (
        <div className="grid cols-4">
          <Stat label="Signal activity" value={sc.impact.toFixed(2)} help="Weighted count of the actor's signals." />
          <Stat label="Cost-weighted" value={sc.credibility.toFixed(2)} help="Signal activity after discounting low-cost signals." />
          <Stat label="Capability–Legitimacy" value={sc.authority.toFixed(2)} help="1 = pure capability evidence, 0 = pure legitimacy." />
          <Stat
            label="Signal trend"
            value={`${sc.momentum >= 0 ? "+" : ""}${sc.momentum}`}
            deltaDir={sc.momentum > 0 ? "up" : sc.momentum < 0 ? "down" : "flat"}
            delta={`${sc.signal_count_this_week} this wk vs ${sc.signal_count_prev_week} prev`}
          />
        </div>
      ) : (
        <Empty>No signals collected for this actor in the current window. Widen the window in the top-right.</Empty>
      )}

      {mix.length > 0 && (
        <Card style={{ marginTop: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>Signal mix</h3>
          <HBar data={mix} dataKey="count" categoryKey="label" height={Math.max(160, mix.length * 38)} />
        </Card>
      )}

      <h2>Evidence ({data.signals?.length || 0})</h2>
      {(data.signals || []).map((s: any) => (
        <Card key={s.id} style={{ marginBottom: "0.75rem" }}>
          <div className="pill-row" style={{ marginBottom: "0.4rem" }}>
            <strong>{s.dimension_label}</strong>
            <ChannelBadge channel={s.is_technical ? "capability" : "legitimacy"} />
            <CostBadge cost={s.cost_class || "medium"} />
            <span className="badge" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
              {s.source_kind_label}
            </span>
            <span className="faint small">confidence {Number(s.confidence).toFixed(2)}</span>
          </div>
          {s.title && <div style={{ fontWeight: 600 }}>{s.title}</div>}
          {s.summary && <div className="small">{s.summary}</div>}
          {s.evidence_quote && (
            <blockquote className="small muted" style={{ borderLeft: "3px solid var(--border)", margin: "0.5rem 0 0", padding: "0.1rem 0 0.1rem 0.75rem" }}>
              “{s.evidence_quote}”
            </blockquote>
          )}
          <div className="small" style={{ marginTop: "0.4rem" }}>
            <a href={s.source_url} target="_blank" rel="noreferrer">Open source ↗</a>
          </div>
        </Card>
      ))}
    </>
  );
}
