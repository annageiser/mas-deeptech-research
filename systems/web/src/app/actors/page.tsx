import { api } from "@/lib/api";
import { Card, Empty, PageHeader, ActorLink } from "@/components/ui";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string } };

export default async function Actors({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "30");

  let scores: any[] = [];
  let actors: any[] = [];
  try {
    [scores, actors] = await Promise.all([
      api.scores(system, days).then((r) => r.scores),
      api.actors().then((r) => r.actors),
    ]);
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  const scoreBySlug = new Map(scores.map((s) => [s.actor_slug, s]));
  // group actors by category; show score where present
  const byCat = new Map<string, any[]>();
  for (const a of actors) {
    const arr = byCat.get(a.category) || [];
    arr.push(a);
    byCat.set(a.category, arr);
  }
  const catLabel: Record<string, string> = {
    national_initiative: "National initiatives",
    university_or_research_hub: "Universities & research hubs",
    ecosystem_builder: "Ecosystem builders",
    private_company: "Private companies",
    government: "Government",
  };

  return (
    <>
      <PageHeader title="Actors" lead="The full Swiss quantum-computing actor list. Pick one for its profile, signal mix, timeline and evidence." />
      {[...byCat.entries()].map(([cat, list]) => (
        <Card key={cat} style={{ marginBottom: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>{catLabel[cat] || cat}</h3>
          <table>
            <thead>
              <tr>
                <th>Actor</th>
                <th className="num">Signals</th>
                <th className="num">Impact</th>
                <th className="num">Δ wk</th>
              </tr>
            </thead>
            <tbody>
              {list
                .sort((a, b) => (scoreBySlug.get(b.slug)?.impact || 0) - (scoreBySlug.get(a.slug)?.impact || 0))
                .map((a) => {
                  const sc = scoreBySlug.get(a.slug);
                  return (
                    <tr key={a.slug}>
                      <td><ActorLink slug={a.slug} name={a.name} system={system} days={String(days)} /></td>
                      <td className="num">{sc?.signal_count ?? 0}</td>
                      <td className="num">{sc ? sc.impact.toFixed(2) : "—"}</td>
                      <td className="num faint">{sc ? sc.momentum : "—"}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </Card>
      ))}
    </>
  );
}
