import { api } from "@/lib/api";
import { Card, Stat, Empty, PageHeader, ActorLink } from "@/components/ui";
import { Donut, Scatter2D } from "@/components/charts";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string } };

export default async function Signalling({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");

  let sig;
  try {
    sig = await api.signalling(system, days);
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  const costData = [
    { name: "High-cost (hard to fake)", value: sig.cost_mix.high || 0, color: "#15803d" },
    { name: "Medium-cost", value: sig.cost_mix.medium || 0, color: "#ca8a04" },
    { name: "Low-cost (cheap talk)", value: sig.cost_mix.low || 0, color: "#dc2626" },
  ];
  const channelData = [
    { name: "Capability evidence", value: sig.channel_mix.capability || 0, color: "#2563eb" },
    { name: "Legitimacy evidence", value: sig.channel_mix.legitimacy || 0, color: "#d97706" },
  ];
  const scatter = sig.actors
    .filter((a) => a.signal_count >= 1)
    .map((a) => ({
      name: a.name || a.actor_slug,
      cheap_talk: Number((a.cheap_talk_ratio * 100).toFixed(1)),
      credibility: a.credibility,
      impact: a.impact,
    }));

  return (
    <>
      <PageHeader
        title="Signalling theory"
        lead="In a market with no shared prices, shares or benchmarks, actors articulate their position through observable signals. A signal informs to the extent it is costly and hard to fake. The core question: do actors substitute cheap talk for costly capability evidence?"
      />

      <div className="grid cols-3">
        <Stat
          label="Ecosystem cheap-talk ratio"
          value={`${Math.round(sig.ecosystem_cheap_talk_ratio * 100)}%`}
          help="Share of all signals that are low-cost market positioning."
        />
        <Stat label="High-cost signals" value={sig.cost_mix.high || 0} help="Patents, funding, peer-reviewed research, infrastructure." />
        <Stat label="Cheap-talk signals" value={sig.cost_mix.low || 0} help="Roadmaps, positioning statements, branding." />
      </div>

      <div className="grid cols-2" style={{ marginTop: "1rem" }}>
        <Card>
          <h3 style={{ marginTop: 0 }}>Signal cost mix</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            Costly signals (Rieger et al. 2025; Suchman 1995) separate genuine capability from cheap talk.
          </p>
          <Donut data={costData} />
        </Card>
        <Card>
          <h3 style={{ marginTop: 0 }}>Capability vs legitimacy channel</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            What an actor can <em>do</em> (Knight &amp; Cavusgil 2004) vs social acceptance (Suchman 1995).
          </p>
          <Donut data={channelData} />
        </Card>
      </div>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Does cheap talk track costly signal?</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Each point is an actor. X = share of their signals that are cheap talk; Y = credibility
          (cost-discounted impact). An actor high-right is loud but lightly-backed; an actor
          high-left is backing its position with costly evidence.
        </p>
        {scatter.length ? (
          <Scatter2D data={scatter} xKey="cheap_talk" yKey="credibility" xLabel="Cheap-talk ratio (%)" yLabel="Credibility (cost-weighted impact)" />
        ) : (
          <div className="empty">No signals in this window yet.</div>
        )}
      </Card>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Per-actor breakdown</h3>
        <table>
          <thead>
            <tr>
              <th>Actor</th>
              <th className="num">Impact</th>
              <th className="num">Credibility</th>
              <th className="num">Cheap-talk %</th>
              <th className="num">High-cost</th>
              <th className="num">Authority</th>
            </tr>
          </thead>
          <tbody>
            {sig.actors.slice(0, 25).map((a) => (
              <tr key={a.actor_slug}>
                <td><ActorLink slug={a.actor_slug} name={a.name || a.actor_slug} system={system} days={String(days)} /></td>
                <td className="num">{a.impact.toFixed(2)}</td>
                <td className="num">{a.credibility.toFixed(2)}</td>
                <td className="num">{Math.round(a.cheap_talk_ratio * 100)}%</td>
                <td className="num">{a.high_cost}</td>
                <td className="num">{a.authority.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <p className="small faint" style={{ marginTop: "1rem" }}>
        Credibility = Σ (dimension weight × confidence × cost multiplier). Cost multipliers: high 1.0,
        medium 0.7, low 0.4. See the <a href="/methodology">methodology</a> for the full model and
        per-dimension grounding.
      </p>
    </>
  );
}
