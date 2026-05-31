// Shapes returned by systems/api (FastAPI). Kept loose where the API enriches.

export type SystemKey = "masfactory" | "hermes";

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
  cost_class?: string;
  is_technical: boolean;
  confidence: number;
  inserted_at: string;
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
  dimension_mix: { dimension: string; label: string; count: number; cost_class: string }[];
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
  dimensions: MetaDimension[];
  category_labels: Record<string, string>;
  category_colors: Record<string, string>;
  system_labels: Record<string, string>;
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

export interface KnowledgeGraph {
  nodes: {
    id: string;
    kind: "actor" | "dimension";
    label: string;
    category?: string;
    category_label?: string;
    color: string;
    size: number;
    dimensions?: number;
  }[];
  edges: { source: string; target: string; weight: number; kind: string; shared?: string[] }[];
}

export interface ReportListItem {
  kind: string;
  period: string;
  file: string;
  title: string;
}
