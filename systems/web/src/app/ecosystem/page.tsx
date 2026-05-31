import { api } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/ui";
import { HBarColored } from "@/components/charts";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string } };

export default async function Ecosystem({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "30");
  let eco;
  try {
    eco = await api.ecosystem(system, days);
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  const cat = eco.category_mix.map((c) => ({ label: c.label, count: c.count, color: c.color }));
  const dim = eco.dimension_mix.map((d) => ({
    label: d.label,
    count: d.count,
    color: d.cost_class === "high" ? "#15803d" : d.cost_class === "low" ? "#dc2626" : "#ca8a04",
  }));

  return (
    <>
      <PageHeader title="Ecosystem map" lead="Where the action is concentrated — which categories of actor generate the most signal, and what kinds of signal dominate." />
      <div className="grid cols-2">
        <Card>
          <h3 style={{ marginTop: 0 }}>Signal by actor category</h3>
          {cat.length ? <HBarColored data={cat} dataKey="count" categoryKey="label" colorKey="color" height={300} /> : <div className="empty">No data.</div>}
        </Card>
        <Card>
          <h3 style={{ marginTop: 0 }}>Signal by type (coloured by cost)</h3>
          {dim.length ? <HBarColored data={dim} dataKey="count" categoryKey="label" colorKey="color" height={300} /> : <div className="empty">No data.</div>}
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
