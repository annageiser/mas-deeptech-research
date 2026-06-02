"""Analyst — writes a short markdown brief per actor.

The brief is what a human researcher (Anna's supervisor, in this case) reads
to sanity-check what the pipeline found in this run.

## Prompt engineering applied
- **Audience anchoring** (Reynolds & McDonell 2021): the instructions
  explicitly name the reader ("a research supervisor scanning in under two
  minutes") so the model picks the right voice / brevity.
- **Output length budget** (Sahoo et al. 2024 §3.4): explicit max-word cap
  prevents the model from padding when signal volume is low.
- **One-shot exemplar** (Brown et al. 2020) so the model's first line
  matches the expected format on first try.
"""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter


ANALYST_INSTRUCTIONS = """You are the Analyst in a Swiss-quantum ecosystem-mapping pipeline.

You receive the surviving classified signals (those the Critic kept) and the
plan that produced them. Write a SHORT markdown brief:

- One section per actor (use `## Actor name`).
- For each actor: 2-5 bullet points, each citing a signal with its dimension
  and a [source](url) link.
- End with a one-line "**Notable this run:**" pointer to the single most
  important signal.

LENGTH BUDGET: 250 words maximum total. If there are fewer than 5 signals,
write fewer paragraphs — do NOT pad with general commentary about the
ecosystem or with restatements of the schema.

The audience is a research supervisor scanning the brief in under two minutes.

## Worked example (target format)

## Swiss Quantum Initiative
- **Funding:** CHF 50M Series B closed with Forestay + Swisscom Ventures
  ([source](https://example.ch/sqi-funding-2026))
- **Partnership:** new joint lab with EPFL announced for QKD applications
  ([source](https://example.ch/sqi-epfl-2026))

## ID Quantique
- **Patents:** WO 2026/000789 — "Quantum random number generator"
  ([source](https://patents.epo.org/...))

**Notable this run:** SQI's Series B is the largest Swiss-quantum private
funding event of the year so far.
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
