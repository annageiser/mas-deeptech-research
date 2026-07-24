// Persona-lens config — the five stakeholder lenses from thesis §3.2 over the
// one shared descriptive signal store. A persona is a *lens*: a prioritised
// subset of the neutral metrics + a framing question + one-click deep links
// into the existing pages with preset filters. No new data; nothing here is
// prescriptive. (Competitor is folded into consultant + corporate.)

import type { ActorScore } from "./types";

export type PersonaId = "investor" | "researcher" | "consultant" | "corporate" | "government";

export interface MetricSpec {
  /** glossary key (drives the <Term> tooltip) */
  glossaryKey: string;
  /** ActorScore field the value comes from */
  field: keyof ActorScore;
  /** compact column header */
  header: string;
  fmt: (v: number) => string;
}

// Neutral metric column specs, keyed by glossary key. Formulas/labels match the
// rest of the dashboard after the neutral-taxonomy rename.
export const METRICS: Record<string, MetricSpec> = {
  impact: { glossaryKey: "impact", field: "impact", header: "Activity", fmt: (v) => v.toFixed(2) },
  credibility: { glossaryKey: "credibility", field: "credibility", header: "Cost-weighted", fmt: (v) => v.toFixed(2) },
  momentum: { glossaryKey: "momentum", field: "momentum", header: "Trend", fmt: (v) => (v > 0 ? `+${v}` : `${v}`) },
  diversity: { glossaryKey: "diversity", field: "diversity", header: "Breadth", fmt: (v) => `${v}/19` },
  authority: { glossaryKey: "authority", field: "authority", header: "Cap.–Leg.", fmt: (v) => v.toFixed(2) },
  cheap_talk: { glossaryKey: "cheap_talk", field: "cheap_talk_ratio", header: "Low-cost", fmt: (v) => `${Math.round(v * 100)}%` },
};

export interface PersonaQuestion {
  q: string;
  /** base path + preset filters; the page merges in the active system/days */
  href: string;
}

export interface Persona {
  id: PersonaId;
  label: string;
  icon: string; // emoji
  accent: string; // hex
  tagline: string;
  blurb: string;
  caveat?: string;
  /** ordered metric keys featured in this persona's mini-leaderboard */
  metrics: string[];
  /** ActorScore field the mini-leaderboard sorts by, desc */
  sortKey: keyof ActorScore;
  sortLabel: string;
  questions: PersonaQuestion[];
}

export const PERSONAS: Record<PersonaId, Persona> = {
  investor: {
    id: "investor",
    label: "Investor",
    icon: "📈",
    accent: "#2563eb",
    tagline: "Venture, growth, or public-markets analyst",
    blurb:
      "In a market with no revenue or share data, you read observable progress and credible " +
      "commitment. This lens surfaces which actors show substantiated (not low-cost) activity and " +
      "who is accelerating — with the source behind every number.",
    metrics: ["credibility", "momentum", "cheap_talk"],
    sortKey: "credibility",
    sortLabel: "Cost-Weighted Signal Score",
    questions: [
      { q: "Who shows the most substantiated activity?", href: "/leaderboard?sort=credibility" },
      { q: "Who is accelerating right now?", href: "/leaderboard?sort=momentum" },
      { q: "Recent funding-related signals", href: "/signals?dimension=funding_event" },
      { q: "Patent filings", href: "/signals?dimension=patents" },
    ],
  },
  researcher: {
    id: "researcher",
    label: "Researcher",
    icon: "🔬",
    accent: "#059669",
    tagline: "Academic or student entering the field",
    blurb:
      "A navigable, source-attributed map of who works on what, and where technical activity is " +
      "rising. Every claim links back to the arXiv paper, patent, or page it came from.",
    metrics: ["momentum", "diversity", "impact"],
    sortKey: "momentum",
    sortLabel: "Signal Trend",
    questions: [
      { q: "Where is new research being published?", href: "/signals?dimension=publications" },
      { q: "Technical breakthroughs & advances", href: "/signals?dimension=technological_advances" },
      { q: "Who is accelerating on research?", href: "/leaderboard?sort=momentum" },
      { q: "Collection breadth by source", href: "/coverage" },
    ],
  },
  consultant: {
    id: "consultant",
    label: "Management / Consultant",
    icon: "🧭",
    accent: "#7c3aed",
    tagline: "Advising a client on quantum exposure, partners, or targets",
    blurb:
      "A structured read of a benchmark-less market: who is nearest to whom, what the strong actors " +
      "actually do, and where activity concentrates versus where it is thin. Associations are " +
      "correlational within the window — not causal.",
    metrics: ["diversity", "authority", "credibility"],
    sortKey: "diversity",
    sortLabel: "Signal Breadth",
    questions: [
      { q: "Who is nearest to whom? (semantic clusters)", href: "/graph?semantic=1" },
      { q: "Compare actors & the two systems", href: "/compare" },
      { q: "Ecosystem concentration & gaps", href: "/ecosystem" },
      { q: "Breadth leaders (multi-front signalling)", href: "/leaderboard?sort=diversity" },
    ],
  },
  corporate: {
    id: "corporate",
    label: "Corporate",
    icon: "🏢",
    accent: "#d97706",
    tagline: "Self-benchmarking, or a prospective partner / buyer",
    blurb:
      "Where a given actor stands relative to its nearest peers, and which vendors are " +
      "partnership-ready in a capability — with source-attributed proof points and visible gaps " +
      "in an actor's own signalling.",
    metrics: ["authority", "cheap_talk", "diversity"],
    sortKey: "authority",
    sortLabel: "Capability–Legitimacy Ratio",
    questions: [
      { q: "Partnership-ready vendors (ecosystem signals)", href: "/signals?signal_type=community_ecosystem" },
      { q: "Customer co-creation & pilots", href: "/signals?signal_type=customer_cocreation" },
      { q: "Capability vs legitimacy balance", href: "/leaderboard?sort=authority" },
      { q: "Per-actor peer profiles", href: "/actors" },
    ],
  },
  government: {
    id: "government",
    label: "Government / Policy",
    icon: "🏛️",
    accent: "#dc2626",
    tagline: "Federal programme officer",
    blurb:
      "An aggregate, source-attributed view of where activity concentrates, where public funding " +
      "already flows, and where the gaps are across the ecosystem.",
    caveat:
      "Public sources only. This maps observable signalling, not classified capability, and implies " +
      "no completeness — an absent signal is not proof of an absent activity.",
    metrics: ["credibility", "impact", "cheap_talk"],
    sortKey: "credibility",
    sortLabel: "Cost-Weighted Signal Score",
    questions: [
      { q: "Where does public funding flow?", href: "/signals?dimension=funding_event" },
      { q: "Regulatory-recognition activity", href: "/signals?dimension=regulatory_recognition" },
      { q: "Ecosystem standing & coverage gaps", href: "/coverage" },
      { q: "Credible experts (leadership signals)", href: "/signals?dimension=leadership_expertise" },
    ],
  },
};

export const PERSONA_LIST: Persona[] = [
  PERSONAS.investor,
  PERSONAS.researcher,
  PERSONAS.consultant,
  PERSONAS.corporate,
  PERSONAS.government,
];

export function getPersona(id: string): Persona | undefined {
  return (PERSONAS as Record<string, Persona>)[id];
}
