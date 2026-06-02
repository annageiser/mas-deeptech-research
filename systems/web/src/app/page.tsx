import { api } from "@/lib/api";
import { Card, Stat, Empty, PageHeader, ActorLink, CostBadge } from "@/components/ui";
import { HBarColored, Donut } from "@/components/charts";
import Link from "next/link";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string } };

export default async function Overview({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");

  let eco, sig;
  try {
    [eco, sig] = await Promise.all([api.ecosystem(system, days), api.signalling(system, days)]);
  } catch {
    return (
      <Empty>
        Couldn’t reach the data API. If the stack just started, give it a moment and refresh.
      </Empty>
    );
  }

  const s = eco.summary;

  // PRIMARY axis (v0.4.0): Ehrenthal four-signal scheme — what *kind* of
  // signal the ecosystem is sending. Shown as the lead chart so the
  // taxonomy users see first matches the paper's framing.
  const signalTypeData = (eco.signal_type_mix || []).map((t) => ({
    label: t.short_label,
    count: t.count,
    color: t.color,
  }));

  // SECONDARY axis: dimension drill-down, grouped under signal_type. Same
  // colour as the parent signal_type so the relationship is visible.
  const stColorByDim: Record<string, string> = {};
  for (const t of eco.signal_type_mix || []) for (const _ of [t]) {}
  const stColorByKey = Object.fromEntries(
    (eco.signal_type_mix || []).map((t) => [t.signal_type, t.color])
  );
  const dimData = eco.dimension_mix.slice(0, 12).map((d) => ({
    label: d.label,
    count: d.count,
    color: stColorByKey[d.signal_type || ""] || "#94a3b8",
  }));

  const costData = [
    { name: "High-cost", value: sig.cost_mix.high || 0, color: "#15803d" },
    { name: "Medium", value: sig.cost_mix.medium || 0, color: "#ca8a04" },
    { name: "Cheap talk", value: sig.cost_mix.low || 0, color: "#dc2626" },
  ];

  return (
    <>
      <PageHeader
        title="Swiss Quantum Ecosystem"
        lead="Who has impact right now, what signals they send, and how their position is shifting — collected automatically from public sources every day by two independent AI systems."
      />

      <div className="grid cols-4">
        <Stat label="Actors tracked" value={eco.actors_total} help="Full Swiss quantum-computing actor list." />
        <Stat
          label="Active in window"
          value={`${s.n_actors_with_signals} / ${eco.actors_total}`}
          help="Actors with ≥1 signal in the selected window."
        />
        <Stat
          label="Cheap-talk ratio"
          value={`${Math.round(sig.ecosystem_cheap_talk_ratio * 100)}%`}
          help="Share of all signals that are low-cost 'cheap talk' (market positioning). Ehrenthal's research question."
          deltaDir={sig.ecosystem_cheap_talk_ratio > 0.4 ? "down" : "flat"}
          delta={sig.ecosystem_cheap_talk_ratio > 0.4 ? "positioning-heavy" : "evidence-backed"}
        />
        <Stat
          label="Ecosystem momentum"
          value={`${s.total_momentum >= 0 ? "+" : ""}${s.total_momentum}`}
          deltaDir={s.total_momentum > 0 ? "up" : s.total_momentum < 0 ? "down" : "flat"}
          delta="vs previous week"
          help="Signal-count change this week vs last, summed across actors."
        />
      </div>

      <div className="grid cols-2" style={{ marginTop: "1rem" }}>
        <Card>
          <h3 style={{ marginTop: 0 }}>🏆 Top actors by impact</h3>
          <table>
            <thead>
              <tr>
                <th>Actor</th>
                <th>Category</th>
                <th className="num">Impact</th>
                <th className="num">Δ wk</th>
              </tr>
            </thead>
            <tbody>
              {eco.top_actors.slice(0, 8).map((a) => (
                <tr key={a.actor_slug}>
                  <td><ActorLink slug={a.actor_slug} name={a.name || a.actor_slug} system={system} days={String(days)} /></td>
                  <td className="muted small">{a.category_label || "—"}</td>
                  <td className="num">{a.impact.toFixed(2)}</td>
                  <td className="num">
                    <span className={a.momentum > 0 ? "delta up" : a.momentum < 0 ? "delta down" : "faint"}>
                      {a.momentum > 0 ? "▲" : a.momentum < 0 ? "▼" : "·"} {a.momentum}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="small faint" style={{ marginBottom: 0 }}>
            <Link href={`/leaderboard${system !== "both" ? `?system=${system}` : ""}`}>Full leaderboard →</Link>
          </p>
        </Card>

        <Card>
          <h3 style={{ marginTop: 0 }}>Signal credibility mix</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            Costly, hard-to-fake signals (patents, funding, research) vs cheap talk (positioning).
          </p>
          <Donut data={costData} />
        </Card>
      </div>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>What is the ecosystem signalling about?</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Ehrenthal et al. (2026)'s four signal types — the primary lens. See{" "}
          <Link href="/methodology">methodology</Link> for what each covers.
        </p>
        {signalTypeData.length ? (
          <HBarColored data={signalTypeData} dataKey="count" categoryKey="label" colorKey="color" height={200} />
        ) : (
          <div className="empty">No signals in this window yet.</div>
        )}
      </Card>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Sub-categories (drill-down)</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          The 19 sub-dimensions, colour-keyed to their parent signal type above. Cost weighting:{" "}
          <CostBadge cost="high" /> hard-to-fake · <CostBadge cost="medium" /> · <CostBadge cost="low" /> cheap talk.
        </p>
        {dimData.length ? (
          <HBarColored data={dimData} dataKey="count" categoryKey="label" colorKey="color" height={400} />
        ) : (
          <div className="empty">No signals in this window yet.</div>
        )}
      </Card>

      <p className="small faint" style={{ marginTop: "1rem" }}>
        Sources: arXiv (research), actor websites, Google News (third-party coverage). Both AI
        systems write to the same database; see <Link href="/compare">System A vs B</Link> and the{" "}
        <Link href="/methodology">methodology</Link>.
      </p>
    </>
  );
}
