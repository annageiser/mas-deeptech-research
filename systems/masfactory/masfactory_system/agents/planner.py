"""Planner — chooses which actors and which sources to process this run.

It's an Agent (not a CustomNode) so the thesis can later evolve it into a
genuinely-thinking planner without changing the graph wiring.
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

Priority rules of thumb:
- Prefer actors with a non-empty `arxiv_query` AND a homepage (richer signal).
- Spread categories so no single run is dominated by one category.
- Skip actors with neither homepage nor arxiv_query unless quota forces it.
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
