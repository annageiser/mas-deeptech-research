// Shapes returned by systems/api (FastAPI). Kept loose where the API enriches.

// v0.4.37: 'manual' is now a first-class producer alongside the two MAS.
export type SystemKey = "masfactory" | "hermes" | "manual";

// v0.4.37 — editorial training layer.
export interface ManualSignal {
  id: string;
  source_url: string;
  title?: string | null;
  notes?: string | null;
  labels: string[];
  signal_type?: string | null;
  dimension?: string | null;
  actor_slugs: string[];
  created_by: string;
  created_at: string;
  updated_at: string;
  ingested_run_ids?: string[];
  propagated_signal_id?: string | null;
  propagated_at?: string | null;
}

export interface SignalSource {
  id: string;
  url: string;
  kind: "rss" | "atom" | "url";
  label?: string | null;
  notes?: string | null;
  labels: string[];
  actor_slugs: string[];
  enabled: boolean;
  crawl_frequency_hours: number;
  last_fetched_at?: string | null;
  last_status?: string | null;
  last_error?: string | null;
  last_item_count: number;
  created_at: string;
  updated_at: string;
}

export interface Actor {
  slug: string;
  name: string;
  category: string;
  homepage?: string | null;
  arxiv_query?: string | null;
  notes?: string | null;
}

export interface Signal {
  id: string;
  actor_slug: string;
  actor_name?: string;
  system?: string;
  source_kind: string;
  source_kind_label?: string;
  source_url: string;
  title: string;
  summary: string;
  evidence_quote: string;
  dimension: string;
  dimension_label?: string;
  // Ehrenthal et al. (2026) top-level signal type. Optional on older rows
  // that pre-date the v0.4.0 migration (those have `dimension_legacy` set
  // and `signal_type` NULL until the SQL backfill runs).
  signal_type?: string;
  signal_type_label?: string;
  dimension_legacy?: string;
  cost_class?: string;
  is_technical: boolean;
  confidence: number;
  inserted_at: string;
  // v0.4.24 — VADER compound sentiment. Both fields are null on legacy rows
  // (anything before the v0.4.24 migration); newer rows always have both.
  sentiment_score?: number | null;
  sentiment_label?: "positive" | "neutral" | "negative" | null;
}

export interface ActorScore {
  actor_slug: string;
  name?: string;
  category?: string;
  category_label?: string;
  impact: number;
  credibility: number;
  momentum: number;
  diversity: number;
  authority: number;
  cheap_talk_ratio: number;
  high_cost: number;
  low_cost: number;
  signal_count: number;
  signal_count_this_week: number;
  signal_count_prev_week: number;
}

export interface EcosystemResponse {
  summary: {
    n_actors_with_signals: number;
    total_impact: number;
    total_credibility: number;
    total_momentum: number;
    top_actor: string | null;
    top_actor_name?: string;
    top_actor_impact: number;
  };
  actors_total: number;
  // Primary axis (v0.4.0 — Ehrenthal four-signal scheme).
  signal_type_mix?: {
    signal_type: string;
    label: string;
    short_label: string;
    color: string;
    count: number;
  }[];
  // Secondary axis (sub-categories under each signal_type).
  dimension_mix: {
    dimension: string;
    label: string;
    signal_type?: string;       // v0.4.0+
    signal_type_label?: string;
    count: number;
    cost_class: string;
  }[];
  // Orthogonal axis (actor category — unchanged).
  category_mix: { category: string; label: string; count: number; color: string }[];
  top_actors: ActorScore[];
}

export interface SignallingResponse {
  cost_mix: Record<string, number>;
  cost_mix_pct: Record<string, number>;
  channel_mix: Record<string, number>;
  ecosystem_cheap_talk_ratio: number;
  actors: ActorScore[];
}

export interface MetaDimension {
  key: string;
  label: string;
  signal_type?: string;       // v0.4.0+ — Ehrenthal top-level
  signal_type_label?: string;
  channel: string;
  channel_label: string;
  is_technical: boolean;
  weight: number;
  signal_cost: string;
  cost_label: string;
  cost_multiplier: number;
  observability: string;
  description: string;
  grounding: string;
  extension?: boolean;        // true for our two extensions to Ehrenthal's coding scheme
}

export interface MetaSignalType {
  key: string;
  label: string;
  short_label: string;
  description: string;
  grounding: string;
  color: string;
  dimensions: string[]; // dimension keys belonging to this signal_type
}

export interface MetaResponse {
  version: string;
  last_revised?: string;
  channels: { key: string; label: string; description: string }[];
  cost_classes: Record<string, { multiplier: number; label?: string }>;
  signalling_theory: {
    premise?: string;
    cost_principle?: string;
    references?: string[];
  };
  // v0.4.0+ — Ehrenthal four-signal scheme spine.
  signal_types?: MetaSignalType[];
  dimensions: MetaDimension[];
  category_labels: Record<string, string>;
  category_colors: Record<string, string>;
  system_labels: Record<string, string>;
  legacy_dimension_map?: Record<string, string>;
}

export interface CompareResponse {
  per_system: Record<
    string,
    {
      label: string;
      runs: number;
      runs_ok: number;
      runs_error: number;
      signals: number;
      actors: number;
      input_tokens: number;
      output_tokens: number;
      signals_per_1k_tokens: number | null;
    }
  >;
  agreement: {
    actor_slug: string;
    name: string;
    system_a_impact: number;
    system_b_impact: number;
    status: "both" | "only_a" | "only_b";
  }[];
  agreement_counts: { both: number; only_a: number; only_b: number };
}

// B.3 — collection-breadth metric (signals/actor/week per source_kind).
export interface CoverageActor {
  actor_slug: string;
  name: string;
  category?: string | null;
  category_label?: string | null;
  total: number;
  weeks_active: number;
  source_kinds: number;
  by_source_kind: Record<string, number>;
}

export interface CoverageWeek {
  iso_week: string;
  total: number;
  by_source_kind: Record<string, number>;
}

export interface CoverageResponse {
  summary: {
    total_signals: number;
    actors_with_signals: number;
    actors_total: number;
    coverage_pct: number;
    weeks: number;
    source_kinds: number;
  };
  per_source_kind: { source_kind: string; label: string; count: number; pct: number }[];
  per_actor: CoverageActor[];
  weekly: CoverageWeek[];
}

export interface KnowledgeGraphNode {
  id: string;
  // v0.4.40 — adds the 'signal_type' kind for the four Ehrenthal categories
  // when include_taxonomy=true; legacy kinds remain unchanged.
  kind: "actor" | "dimension" | "signal_type";
  label: string;
  // Actor nodes:
  actor_slug?: string;
  category?: string;
  category_label?: string;
  dimensions?: number;
  // Dimension nodes:
  dimension_key?: string;
  signal_type?: string;
  signal_type_label?: string;
  cost_class?: string;
  // Signal-type nodes (v0.4.40):
  signal_type_key?: string;
  short_label?: string;
  // Both:
  color: string;
  size: number;
}

// v0.4.40 — the wire-level edge kind list. Frontend code treats unknown
// strings as no-op (defensive: API may emit new kinds before the client
// is rebuilt). Edge kinds added in v0.4.40 are emitted only when the
// caller opts in via include_taxonomy=true / include_semantic=true.
export type KnowledgeGraphEdgeKind =
  | "actor-dim"           // existing: per-(actor, dimension) signal count
  | "actor-actor"         // existing: shared-dimension co-occurrence
  | "dim-signal-type"     // v0.4.40: taxonomy edge dimension → signal_type
  | "actor-signal-type"   // v0.4.40: aggregated actor → signal_type volume
  | "actor-actor-sim";    // v0.4.40: pgvector cosine similarity edge

export interface KnowledgeGraphEdge {
  source: string;
  target: string;
  weight: number;
  // String at the wire layer (FastAPI returns whatever build_graph_json emits);
  // the renderer narrows it to the discriminated union it cares about.
  kind: KnowledgeGraphEdgeKind | string;
  // actor-dim edges:
  count?: number;
  actor_label?: string;
  dimension_label?: string;
  signal_type?: string;
  signal_type_label?: string;
  cost_class?: string;
  sample_titles?: string[];
  // actor-actor edges:
  actor_a_label?: string;
  actor_b_label?: string;
  shared?: string[];               // shared dimension labels
  shared_signal_types?: string[];  // shared Ehrenthal signal_types
  // v0.4.40 actor-actor-sim edges:
  similarity?: number;             // pgvector cosine in [0, 1]
}

export interface KnowledgeGraph {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

export interface ReportListItem {
  kind: string;
  period: string;
  file: string;
  title: string;
}
