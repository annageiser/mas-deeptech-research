import { api } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/ui";
import GraphCanvas from "@/components/GraphCanvas";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string; threshold?: string } };

export default async function Graph({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");
  const threshold = Number(searchParams.threshold || "2");

  let graph;
  try {
    graph = await api.knowledgeGraph(system, days, threshold);
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  return (
    <>
      <PageHeader
        title="Knowledge graph"
        lead="Inner ring: signal types (Ehrenthal four-signal scheme). Outer ring: actors, grouped by category (colour) and sized by how many distinct signal types they cover. Lines connect actors to the signal types they emit. Hover any node OR edge to inspect: actor-dim edges show the dimension, count, and sample signal titles; actor-actor edges show shared Ehrenthal categories. Tick the peer-edges box to overlay actor↔actor co-occurrence."
      />
      <Card>
        <div className="small muted" style={{ marginBottom: "0.5rem" }}>
          {graph.nodes.length} nodes · {graph.edges.length} edges
        </div>
        <GraphCanvas graph={graph} />
      </Card>
    </>
  );
}
