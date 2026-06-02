"""Planner — chooses which actors and which sources to process this run.

It's an Agent (not a CustomNode) so the thesis can later evolve it into a
genuinely-thinking planner without changing the graph wiring.

## Prompt engineering applied
- **Role priming** + **explicit priority-rules heuristic** (Reynolds &
  McDonell 2021 prompt programming): rules listed by precedence so the
  model has a deterministic tiebreak procedure rather than an internal
  policy that drifts run-to-run.
- **Self-check instruction** (Wei et al. 2022; Sahoo et al. 2024 §3.5):
  the "Before returning, verify ..." line is a lightweight self-critique
  that catches off-list slugs.
"""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter


PLANNER_INSTRUCTIONS = """You are the Planner of a multi-agent pipeline that monitors the Swiss
quantum-computing ecosystem. You receive a JSON list of candidate actors and
a per-run quota. Your job is to:

1. Select the `limit_actors` highest-priority actors for this run.
2. For each, propose which sources to query (`arxiv`, `website`, or both).
3. Return ONLY a strict JSON object — no prose — matching the schema in
   `<plan_json>`.

Priority rules (apply in order, ties broken alphabetically by slug):
1. Prefer actors with a non-empty `arxiv_query` AND a homepage (richer signal).
2. Spread categories so no single run is dominated by one category — aim
   for at most ⌈limit_actors / 2⌉ actors from any single category.
3. Skip actors with neither homepage nor arxiv_query unless quota forces it.

Before returning, verify that:
- Every `slug` you emit appears in the input `candidate_actors` list.
- The output has at most `limit_actors` entries.
- Every entry's `sources` field is a non-empty list.
"""

PLANNER_PROMPT = """<candidate_actors>{candidate_actors_json}</candidate_actors>
<limit_actors>{limit_actors}</limit_actors>

Return a plan with shape:
{{
  "selected": [
    {{"slug": "...", "sources": ["arxiv", "website"]}},
    ...
  ]
}}
"""


PlannerNode = NodeTemplate(
    Agent,
    instructions=PLANNER_INSTRUCTIONS,
    prompt_template=PLANNER_PROMPT,
    pull_keys={
        "candidate_actors_json": "JSON array of candidate actor objects (slug, name, category, homepage, arxiv_query)",
        "limit_actors": "Integer cap on how many actors this run should process",
    },
    push_keys={"plan_json": "JSON plan describing selected actors and per-actor source list"},
    formatters=[ParagraphMessageFormatter(), TaggedFieldMessageFormatter()],
)
