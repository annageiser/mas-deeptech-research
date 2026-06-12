import { api } from "@/lib/api";
import { Card, Stat, Empty, PageHeader, ActorLink } from "@/components/ui";
import { Donut } from "@/components/charts";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string } };

// Stable colour palette for the 5 source_kinds the schema currently allows.
const SOURCE_COLOR: Record<string, string> = {
  arxiv: "#2563eb",      // blue   — academic
  website: "#0891b2",    // teal   — primary
  news: "#d97706",       // amber  — media
  swissreg: "#7c3aed",   // purple — patent
  manual: "#64748b",     // slate  — fallback
};

const colourFor = (key: string) => SOURCE_COLOR[key] || "#94a3b8";

export default async function Coverage({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");

  let cov;
  try {
    cov = await api.coverage(system, days);
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  const { summary, per_source_kind, per_actor, weekly } = cov;

  const sourceDonut = per_source_kind.map((s) => ({
    name: s.label,
    value: s.count,
    color: colourFor(s.source_kind),
  }));

  const gap = per_actor.filter((a) => a.total === 0);
  const covered = per_actor.filter((a) => a.total > 0);

  // Weekly sparkline as a simple per-week mini-bar so the page renders without
  // pulling in a new chart component. Stays readable up to ~13 weeks.
  const maxWeek = weekly.reduce((m, w) => (w.total > m ? w.total : m), 0) || 1;

  return (
    <>
      <PageHeader
        title="Coverage"
        lead="Are we collecting evenly across the 40 seeded actors and across all four
              source types (arXiv / website / news / patent)? A skewed corpus weakens
              every downstream signalling-theory claim."
      />

      <div className="grid cols-4">
        <Stat
          label="Total signals"
          value={summary.total_signals}
          help={`Over the last ${days} days, in the selected system filter.`}
        />
        <Stat
          label="Actor coverage"
          value={`${summary.coverage_pct}%`}
          help={`${summary.actors_with_signals} of ${summary.actors_total} seeded actors produced ≥1 signal.`}
        />
        <Stat
          label="Weeks active"
          value={summary.weeks}
          help="Distinct ISO weeks with at least one signal."
        />
        <Stat
          label="Source kinds"
          value={`${summary.source_kinds} / 5`}
          help="Distinct values of signals.source_kind. The schema allows 5."
        />
      </div>

      <div className="grid cols-2" style={{ marginTop: "1rem" }}>
        <Card>
          <h3 style={{ marginTop: 0 }}>Source-kind mix</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            A heavy long-tail on one source signals a collection bias — e.g.
            “website only” means we miss what arXiv and news reveal.
          </p>
          {sourceDonut.length ? <Donut data={sourceDonut} /> : <Empty>No signals.</Empty>}
        </Card>

        <Card>
          <h3 style={{ marginTop: 0 }}>Weekly throughput</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            Signals collected per ISO week. Looks for steady cadence and flags
            gaps where the cron run produced nothing.
          </p>
          {weekly.length ? (
            <table>
              <thead>
                <tr>
                  <th>Week</th>
                  <th className="num">Signals</th>
                  <th>Distribution</th>
                </tr>
              </thead>
              <tbody>
                {weekly.slice(-13).reverse().map((w) => (
                  <tr key={w.iso_week}>
                    <td className="small">{w.iso_week}</td>
                    <td className="num">{w.total}</td>
                    <td>
                      <div
                        aria-hidden
                        style={{
                          height: 8,
                          background: "var(--bar-bg, #e2e8f0)",
                          borderRadius: 4,
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            width: `${(100 * w.total) / maxWeek}%`,
                            height: "100%",
                            background: "#0891b2",
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>No weekly data.</Empty>
          )}
        </Card>
      </div>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Per-actor coverage</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          One row per seeded actor. Distribution column shows the source mix
          inside that actor’s signal pool. A row with everything in one bar is
          fine for arXiv-only research labs, suspicious for portfolio-style VCs.
        </p>
        <table>
          <thead>
            <tr>
              <th>Actor</th>
              <th>Category</th>
              <th className="num">Signals</th>
              <th className="num">Weeks</th>
              <th className="num">Source kinds</th>
              <th>Distribution</th>
            </tr>
          </thead>
          <tbody>
            {covered.map((a) => {
              const max = a.total || 1;
              return (
                <tr key={a.actor_slug}>
                  <td>
                    <ActorLink
                      slug={a.actor_slug}
                      name={a.name}
                      system={system}
                      days={String(days)}
                    />
                  </td>
                  <td className="small muted">{a.category_label || "—"}</td>
                  <td className="num">{a.total}</td>
                  <td className="num">{a.weeks_active}</td>
                  <td className="num">{a.source_kinds}</td>
                  <td>
                    <div style={{ display: "flex", gap: 2, height: 10 }}>
                      {Object.entries(a.by_source_kind)
                        .sort((x, y) => y[1] - x[1])
                        .map(([kind, n]) => (
                          <div
                            key={kind}
                            title={`${kind}: ${n}`}
                            style={{
                              width: `${(100 * n) / max}%`,
                              background: colourFor(kind),
                              borderRadius: 2,
                            }}
                          />
                        ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      {gap.length > 0 && (
        <Card style={{ marginTop: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>Gap: actors with zero signals in window</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            Seeded in <code>data/raw/actors.yaml</code> but no signal collected
            in the last {days} days. Either the collectors missed them or they
            genuinely had nothing to say — worth a manual spot-check.
          </p>
          <ul className="small">
            {gap.map((a) => (
              <li key={a.actor_slug}>
                {a.name}
                {a.category_label ? <span className="muted"> — {a.category_label}</span> : null}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <p className="small faint" style={{ marginTop: "1rem" }}>
        Coverage = (actors with ≥1 signal in the window) / (actors seeded). A
        single ISO week is Monday–Sunday; <code>iso_week</code> is calculated
        from <code>signals.inserted_at</code>.
      </p>
    </>
  );
}
