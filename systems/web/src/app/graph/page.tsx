import { api } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/ui";
import GraphCanvas from "@/components/GraphCanvas";

export const dynamic = "force-dynamic";

// v0.4.40 — three additional query params for the additive graph layers.
// All default off so the page stays bit-identical to its v0.4.0 behaviour
// unless the operator opts in via URL.
type SP = {
  searchParams: {
    system?: string;
    days?: string;
    threshold?: string;
    taxonomy?: string;       // v0.4.40 — '1' to render signal_type nodes + taxonomy edges
    semantic?: string;       // v0.4.40 — '1' to render pgvector cosine actor↔actor edges
    sim_threshold?: string;  // v0.4.40 — float in [0, 1], default 0.85
  };
};

function flag(v?: string): boolean {
  return v === "1" || v === "true" || v === "yes";
}

export default async function Graph({ searchParams }: SP) {
  const system = searchParams.system || "both";
  const days = Number(searchParams.days || "90");
  const threshold = Number(searchParams.threshold || "2");
  const includeTaxonomy = flag(searchParams.taxonomy);
  const includeSemantic = flag(searchParams.semantic);
  const semanticThreshold = Number(searchParams.sim_threshold || "0.85");

  let graph;
  try {
    graph = await api.knowledgeGraph(system, days, threshold, {
      include_taxonomy: includeTaxonomy,
      include_semantic: includeSemantic,
      semantic_threshold: semanticThreshold,
    });
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  return (
    <>
      <PageHeader
        title="Knowledge graph"
        lead="Inner ring: signal types (Ehrenthal four-signal scheme). Outer ring: actors, grouped by category (colour) and sized by how many distinct signal types they cover. Lines connect actors to the signal types they emit. Hover any node OR edge to inspect. Tick a layer checkbox to overlay actor↔actor peer links, the four-category taxonomy, or pgvector-cosine semantic neighbours."
      />
      <Card>
        <div className="small muted" style={{ marginBottom: "0.5rem" }}>
          {graph.nodes.length} nodes · {graph.edges.length} edges
          {includeTaxonomy && " · taxonomy on"}
          {includeSemantic && " · semantic on"}
        </div>
        <LayerLinks
          system={system}
          days={days}
          threshold={threshold}
          includeTaxonomy={includeTaxonomy}
          includeSemantic={includeSemantic}
          semanticThreshold={semanticThreshold}
        />
        <GraphCanvas graph={graph} />
      </Card>
    </>
  );
}

/**
 * Tiny server-rendered toggle row. Each link rewrites a single query
 * param so the page is a plain GET — no client-side state, no extra
 * round trip beyond the existing knowledge-graph fetch.
 */
function LayerLinks({
  system, days, threshold,
  includeTaxonomy, includeSemantic, semanticThreshold,
}: {
  system: string;
  days: number;
  threshold: number;
  includeTaxonomy: boolean;
  includeSemantic: boolean;
  semanticThreshold: number;
}) {
  const baseParams = (overrides: Record<string, string>) => {
    const params = new URLSearchParams();
    if (system && system !== "both") params.set("system", system);
    params.set("days", String(days));
    params.set("threshold", String(threshold));
    if (includeTaxonomy) params.set("taxonomy", "1");
    if (includeSemantic) params.set("semantic", "1");
    if (semanticThreshold !== 0.85) params.set("sim_threshold", String(semanticThreshold));
    for (const [k, v] of Object.entries(overrides)) {
      if (v === "") params.delete(k);
      else params.set(k, v);
    }
    return params.toString();
  };

  const linkStyle = (active: boolean): React.CSSProperties => ({
    fontSize: "0.8rem",
    padding: "0.2rem 0.55rem",
    borderRadius: 999,
    background: active ? "var(--brand, #2563eb)" : "transparent",
    color: active ? "#fff" : "var(--text-muted)",
    border: `1px solid ${active ? "transparent" : "var(--border)"}`,
    textDecoration: "none",
    marginRight: "0.4rem",
  });

  return (
    <div style={{ marginBottom: "0.65rem" }}>
      <a
        href={`?${baseParams({ taxonomy: includeTaxonomy ? "" : "1" })}`}
        style={linkStyle(includeTaxonomy)}
      >
        Taxonomy hierarchy
      </a>
      <a
        href={`?${baseParams({ semantic: includeSemantic ? "" : "1" })}`}
        style={linkStyle(includeSemantic)}
      >
        Semantic similarity
      </a>
      <span className="small faint" style={{ marginLeft: "0.4rem" }}>
        (v0.4.40 — opt-in additive layers; default off)
      </span>
    </div>
  );
}
