// Central glossary for the metric terms + calculations surfaced across the
// dashboard. Rendered as hover/focus tooltips via the <Term> component
// (see components/ui.tsx). Kept in sync with the score formulas on the
// /methodology page — that page is the human-readable single source of
// truth; this is its tooltip-sized restatement so a reader never has to
// leave the table they're looking at to know what a column means.

export type GlossaryEntry = {
  /** Bold heading shown at the top of the tooltip. */
  title: string;
  /** Optional formula, rendered in a <code> block. Matches /methodology. */
  formula?: string;
  /** Plain-language explanation of what the number tells you. */
  body: string;
};

export const GLOSSARY: Record<string, GlossaryEntry> = {
  impact: {
    title: "Signal Activity Score",
    formula: "Σ (weight × confidence)",
    body:
      "How much an observer should update their view of an actor, summed " +
      "over every signal. Weight is the dimension's importance; confidence " +
      "is how sure the classifier is the signal is real.",
  },
  credibility: {
    title: "Cost-Weighted Signal Score",
    formula: "Σ (weight × confidence × cost_mult)",
    body:
      "The Signal Activity Score after discounting low-cost signals. " +
      "Hard-to-fake signals (patents, funding, peer-reviewed research) keep " +
      "most of their weight; low-cost positioning is multiplied down.",
  },
  momentum: {
    title: "Signal Trend",
    formula: "signals_7d − prev_7d",
    body:
      "Signal count in the last 7 days minus the 7 days before. Positive = " +
      "accelerating, negative = cooling. Shown in the Δ-week column.",
  },
  diversity: {
    title: "Signal Breadth",
    formula: "distinct dimensions",
    body:
      "How many of the signal dimensions an actor is active on. High = " +
      "broad, multi-front signalling; low = a narrow, single-note story.",
  },
  authority: {
    title: "Capability–Legitimacy Ratio",
    formula: "(cap + 1) / (cap + leg + 2)",
    body:
      "Balance between capability signals (what an actor can technically " +
      "do) and legitimacy signals (endorsements, partnerships). Near 1 = " +
      "capability-led; near 0 = legitimacy-led. Laplace-smoothed.",
  },
  cheap_talk: {
    title: "Low-Cost Signal Share",
    formula: "low_cost / total",
    body:
      "Share of an actor's signals that are low-cost and hard to verify — " +
      "claims that are easy to make. A high share means positioning is " +
      "substituting for evidence.",
  },
};
