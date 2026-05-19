"""Critic — drops low-confidence and duplicate signals before persistence."""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter


CRITIC_INSTRUCTIONS = """You are the Critic in a Swiss-quantum ecosystem-mapping pipeline.

You receive a JSON array of classified signals. Your job is to decide, for
each one, whether it should be kept or dropped, and why.

Rules:
- Drop any signal with confidence < 0.4.
- Drop any signal whose evidence_quote is generic boilerplate
  ("leading provider", "we are committed to ...", etc.).
- Mark exact-meaning duplicates within the input batch: keep the first, set
  `keep=false` and `duplicate_of=<earlier_index>` on the later ones.
- Be conservative: if in doubt, keep the signal — the Analyst can still
  ignore it. The thesis values recall here.

Return ONLY JSON.
"""

CRITIC_PROMPT = """<classified>{classified_json}</classified>

Return JSON of shape:
{{
  "decisions": [
    {{
      "signal_index": 0,
      "keep": true,
      "reason": "...",
      "duplicate_of": null
    }}
  ]
}}
"""


CriticNode = NodeTemplate(
    Agent,
    instructions=CRITIC_INSTRUCTIONS,
    prompt_template=CRITIC_PROMPT,
    pull_keys={"classified_json": "JSON object with `classified` array of ClassifiedSignal"},
    push_keys={"critique_json": "JSON object with `decisions` array of CritiqueDecision"},
    formatters=[ParagraphMessageFormatter(), TaggedFieldMessageFormatter()],
)
