import { api } from "@/lib/api";
import { Card, Empty, PageHeader, ActorLink, Bar } from "@/components/ui";
import { Scatter2D } from "@/components/charts";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string; sort?: string } };

const SORTS: Record<string, { label: string; key: string }> = {
  impact: { label: "Impact", key: "impact" },
  credibility: { label: "Credibility", key: "credibility" },
  momentum: { label: "Momentum", key: "momentum" },
  diversity: { label: "Diversity", key: "diversity" },
  authority: { label: "Authority", key: "authority" },
};

export default async function Leaderboard({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");
  const sort = SORTS[searchParams.sort || "impact"] ? searchParams.sort || "impact" : "impact";

  let scores;
  try {
    scores = (await api.scores(system, days)).scores;
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }
  if (!scores.length) return <Empty>No signals in this window. Widen the time window in the top-right.</Empty>;

  const sorted = [...scores].sort((a: any, b: any) => (b[SORTS[sort].key] ?? 0) - (a[SORTS[sort].key] ?? 0));
  const maxImpact = Math.max(...scores.map((s) => s.impact), 1);
  const scatter = scores.map((s) => ({ name: s.name || s.actor_slug, impact: s.impact, momentum: s.momentum }));

  const qbase = (extra: Record<string, string>) => {
    const q = new URLSearchParams();
    if (system !== "both") q.set("system", system);
    if (days !== 30) q.set("days", String(days));
    Object.entries(extra).forEach(([k, v]) => q.set(k, v));
    const s = q.toString();
    return s ? `?${s}` : "";
  };

  return (
    <>
      <PageHeader
        title="Impact leaderboard"
        lead="Five lenses on what 'impact' means in a deep-tech market with no prices or share data. Credibility discounts cheap talk; authority is the capability-vs-legitimacy balance."
      />

      <div className="filters" style={{ marginBottom: "1rem" }}>
        <span className="small muted">Sort by:</span>
        <div className="seg">
          {Object.entries(SORTS).map(([k, v]) => (
            <a key={k} href={`/leaderboard${qbase({ sort: k })}`} className={k === sort ? "active" : ""} style={{ padding: "0.35rem 0.7rem", borderRadius: 6 }}>
              {v.label}
            </a>
          ))}
        </div>
      </div>

      <Card>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Actor</th>
              <th>Category</th>
              <th className="num">Impact</th>
              <th style={{ width: 120 }}>Impact</th>
              <th className="num">Credibility</th>
              <th className="num">Δ wk</th>
              <th className="num">Dims</th>
              <th className="num">Authority</th>
              <th className="num">Cheap-talk</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((a, i) => (
              <tr key={a.actor_slug}>
                <td className="faint">{i + 1}</td>
                <td><ActorLink slug={a.actor_slug} name={a.name || a.actor_slug} system={system} days={String(days)} /></td>
                <td className="muted small">{a.category_label || "—"}</td>
                <td className="num">{a.impact.toFixed(2)}</td>
                <td><Bar value={a.impact} max={maxImpact} /></td>
                <td className="num">{a.credibility.toFixed(2)}</td>
                <td className="num">
                  <span className={a.momentum > 0 ? "delta up" : a.momentum < 0 ? "delta down" : "faint"}>
                    {a.momentum > 0 ? "▲" : a.momentum < 0 ? "▼" : "·"} {a.momentum}
                  </span>
                </td>
                <td className="num">{a.diversity}/9</td>
                <td className="num">{a.authority.toFixed(2)}</td>
                <td className="num">{Math.round(a.cheap_talk_ratio * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Impact vs momentum</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Top-right = strong &amp; accelerating. Bottom-right = strong but cooling. Top-left = small but rising.
        </p>
        <Scatter2D data={scatter} xKey="impact" yKey="momentum" xLabel="Impact" yLabel="Momentum (Δ vs prev week)" />
      </Card>
    </>
  );
}
