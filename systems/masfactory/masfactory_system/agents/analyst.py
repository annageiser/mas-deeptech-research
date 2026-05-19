"""Analyst — writes a short markdown brief per actor.

The brief is what a human researcher (Anna's supervisor, in this case) reads
to sanity-check what the pipeline found in this run.
"""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter


ANALYST_INSTRUCTIONS = """You are the Analyst in a Swiss-quantum ecosystem-mapping pipeline.

You receive the surviving classified signals (those the Critic kept) and the
plan that produced them. Write a SHORT markdown brief:

- One section per actor.
- For each actor: 2-5 bullet points, each citing a signal with its dimension
  and a [source](url) link.
- End with a one-line "Notable this run:" pointer to the single most
  important signal.

The audience is a research supervisor scanning the brief in under two minutes.
"""

ANALYST_PROMPT = """<plan>{plan_json}</plan>
<surviving_signals>{surviving_signals_json}</surviving_signals>

Return only the markdown brief, no JSON wrapper."""


AnalystNode = NodeTemplate(
    Agent,
    instructions=ANALYST_INSTRUCTIONS,
    prompt_template=ANALYST_PROMPT,
    pull_keys={
        "plan_json": "JSON plan from the Planner",
        "surviving_signals_json": "JSON array of ClassifiedSignal kept by the Critic",
    },
    push_keys={"brief_md": "Markdown brief for human consumption"},
    formatters=[ParagraphMessageFormatter(), TaggedFieldMessageFormatter()],
)
