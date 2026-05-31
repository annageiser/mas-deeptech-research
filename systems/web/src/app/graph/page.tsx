import { api } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/ui";
import GraphCanvas from "@/components/GraphCanvas";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string; threshold?: string } };

export default async function Graph({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "30");
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
        lead="Inner ring: signal types. Outer ring: actors (coloured by category, sized by how many distinct signal types they cover). Lines connect actors to the signal types they emit, and actors to peers that share signal types."
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
