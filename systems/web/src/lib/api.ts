// Server-side data fetchers. Called from React Server Components.
// In the browser, relative /api/* is proxied by Caddy → api container.
// On the server (RSC), we hit API_INTERNAL_URL directly (docker network).

import type {
  Actor,
  ActorScore,
  CompareResponse,
  CoverageResponse,
  EcosystemResponse,
  InsightsResponse,
  KnowledgeGraph,
  MetaResponse,
  ReportListItem,
  Signal,
  SignallingResponse,
} from "./types";

const INTERNAL = process.env.API_INTERNAL_URL || "http://api:8000";

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${INTERNAL}${path}`;
  // no-store → render at request time against the live API (the API has its own
  // 60s TTL cache over Supabase, so this doesn't hammer the database). Without
  // this, pages get prerendered statically at build time and freeze.
  const res = await fetch(url, { ...init, cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${path} → ${res.status}`);
  }
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | number | undefined>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "" && v !== "both") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  meta: () => get<MetaResponse>("/api/meta"),
  actors: () => get<{ actors: Actor[] }>("/api/actors"),
  ecosystem: (system?: string, days = 30) =>
    get<EcosystemResponse>(`/api/ecosystem${qs({ system, days })}`),
  scores: (system?: string, days = 30) =>
    get<{ scores: ActorScore[] }>(`/api/scores${qs({ system, days })}`),
  signalling: (system?: string, days = 30) =>
    get<SignallingResponse>(`/api/signalling${qs({ system, days })}`),
  signals: (params: Record<string, string | number | undefined>) =>
    get<{ signals: Signal[]; count: number }>(`/api/signals${qs(params)}`),
  actor: (slug: string, system?: string, days = 30) =>
    get<any>(`/api/actor/${encodeURIComponent(slug)}${qs({ system, days })}`),
  compare: (days = 30) => get<CompareResponse>(`/api/compare${qs({ days })}`),
  coverage: (system?: string, days = 90) =>
    get<CoverageResponse>(`/api/coverage${qs({ system, days })}`),
  insights: (persona?: string, system?: string, days = 90) =>
    get<InsightsResponse>(`/api/insights${qs({ persona, system, days })}`),
  knowledgeGraph: (
    system?: string,
    days = 30,
    threshold = 2,
    // v0.4.40 — additive layers. Default off so legacy callers see the
    // exact same response shape.
    options?: {
      include_taxonomy?: boolean;
      include_semantic?: boolean;
      semantic_threshold?: number;
    },
  ) =>
    get<KnowledgeGraph>(
      `/api/knowledge-graph${qs({
        system,
        days,
        threshold,
        include_taxonomy: options?.include_taxonomy ? 1 : undefined,
        include_semantic: options?.include_semantic ? 1 : undefined,
        semantic_threshold: options?.semantic_threshold,
      })}`,
    ),
  reports: (kind?: string) => get<{ reports: ReportListItem[] }>(`/api/reports${qs({ kind })}`),
  report: (kind: string, period: string, file: string) =>
    get<{ markdown: string }>(`/api/reports${qs({ kind, period, file })}`),
  health: () => get<{ ok: boolean }>("/api/health"),
};

export const COST_COLOR: Record<string, string> = {
  high: "#15803d", // green — costly / credible
  medium: "#ca8a04", // amber
  low: "#dc2626", // red — low-cost
};
