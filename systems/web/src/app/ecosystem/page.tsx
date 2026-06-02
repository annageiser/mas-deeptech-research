import { api } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/ui";
import { HBarColored } from "@/components/charts";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string } };

export default async function Ecosystem({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");
  let eco;
  try {
    eco = await api.ecosystem(system, days);
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  const cat = eco.category_mix.map((c) => ({ label: c.label, count: c.count, color: c.color }));

  // PRIMARY (v0.4.0): Ehrenthal four-signal scheme — what kind of signal.
  const signalType = (eco.signal_type_mix || []).map((t) => ({
    label: t.short_label,
    count: t.count,
    color: t.color,
  }));

  // SECONDARY: 19 dimensions colour-keyed to their parent signal_type so
  // the relationship between the two views is visually clear. Falls back to
  // cost-class colouring for any dimension that didn't get a signal_type
  // (would only happen with un-migrated legacy rows).
  const stColorByKey = Object.fromEntries(
    (eco.signal_type_mix || []).map((t) => [t.signal_type, t.color])
  );
  const dim = eco.dimension_mix.map((d) => ({
    label: d.label,
    count: d.count,
    color:
      stColorByKey[d.signal_type || ""] ||
      (d.cost_class === "high" ? "#15803d" : d.cost_class === "low" ? "#dc2626" : "#ca8a04"),
  }));

  return (
    <>
      <PageHeader
        title="Ecosystem map"
        lead="What kinds of signal the Swiss quantum ecosystem is sending — primary view by Ehrenthal et al. (2026)'s four-signal scheme, with sub-categories underneath."
      />

      <Card>
        <h3 style={{ marginTop: 0 }}>Signal type (Ehrenthal four-signal scheme)</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Four top-level categories from <em>"Global Strategic Marketing When Performance Is
          Noncommensurable"</em> (2026). Hover the knowledge-graph nodes on{" "}
          <a href={`/graph${system !== "both" ? `?system=${system}` : ""}`}>/graph</a> for a
          per-actor view of the same colours.
        </p>
        {signalType.length ? (
          <HBarColored data={signalType} dataKey="count" categoryKey="label" colorKey="color" height={220} />
        ) : (
          <div className="empty">No signals in this window.</div>
        )}
      </Card>

      <div className="grid cols-2" style={{ marginTop: "1rem" }}>
        <Card>
          <h3 style={{ marginTop: 0 }}>Sub-categories</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            The 19 sub-dimensions, colour-keyed to their parent signal type above.
          </p>
          {dim.length ? <HBarColored data={dim} dataKey="count" categoryKey="label" colorKey="color" height={420} /> : <div className="empty">No data.</div>}
        </Card>
        <Card>
          <h3 style={{ marginTop: 0 }}>Signal by actor category</h3>
          <p className="small muted" style={{ marginTop: 0 }}>
            Where the signal volume sits across the four Swiss-actor categories.
          </p>
          {cat.length ? <HBarColored data={cat} dataKey="count" categoryKey="label" colorKey="color" height={300} /> : <div className="empty">No data.</div>}
        </Card>
      </div>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Category leaders</h3>
        <table>
          <thead>
            <tr><th>Actor</th><th>Category</th><th className="num">Impact</th><th className="num">Signals</th></tr>
          </thead>
          <tbody>
            {eco.top_actors.map((a) => (
              <tr key={a.actor_slug}>
                <td>{a.name || a.actor_slug}</td>
                <td className="muted small">{a.category_label || "—"}</td>
                <td className="num">{a.impact.toFixed(2)}</td>
                <td className="num">{a.signal_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
