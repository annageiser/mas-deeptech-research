"""Classifier — labels each candidate against the signal taxonomy."""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter

from ..classification import schema_as_prompt_block


CLASSIFIER_INSTRUCTIONS = f"""You are the Classifier in a Swiss-quantum ecosystem-mapping pipeline.

You receive a JSON array of signal *candidates*. For each candidate you must
assign:
- `signal_type`: one of {{legitimacy, customer_cocreation, community_ecosystem, future_trajectory}} (Ehrenthal et al. 2026 four-signal scheme).
- `dimension`: one of the sub-category keys under that signal_type (taxonomy below).
- `is_technical`: whether that dimension is a technical signal (taxonomy below).
- `confidence`: float in [0, 1] for your label confidence.

CRITICAL: PRESERVE every input field unchanged in your output — `actor_slug`,
`source_kind`, `source_url`, `title`, `summary`, `evidence_quote` MUST be
copied verbatim from the input. NEVER rewrite or "fix" an actor_slug. If you
think the attribution is wrong, lower the `confidence` instead.

{schema_as_prompt_block()}

Reasoning recipe:
  1. Read the evidence_quote. Ask: which of the four signal_types is the
     vendor *primarily* communicating with this content?
  2. Within that signal_type, pick the matching sub-category (dimension).
  3. If the evidence supports two signal_types equally, pick the one with
     the higher signal_cost (we prefer the credibility-grounded reading).
  4. If no dimension fits, drop the candidate. Recall matters but a
     misclassified signal contaminates the whole schema.

Return ONLY JSON. Preserve the order of the input array.
"""

CLASSIFIER_PROMPT = """<candidates>{candidates_json}</candidates>

Return JSON of shape:
{{
  "classified": [
    {{
      "actor_slug": "...",
      "source_kind": "...",
      "source_url": "...",
      "title": "...",
      "summary": "...",
      "evidence_quote": "...",
      "signal_type": "...",
      "dimension": "...",
      "is_technical": true,
      "confidence": 0.0
    }}
  ]
}}
"""


ClassifierNode = NodeTemplate(
    Agent,
    instructions=CLASSIFIER_INSTRUCTIONS,
    prompt_template=CLASSIFIER_PROMPT,
    pull_keys={"candidates_json": "JSON object with `candidates` array"},
    push_keys={"classified_json": "JSON object with `classified` array of ClassifiedSignal"},
    formatters=[ParagraphMessageFormatter(), TaggedFieldMessageFormatter()],
)
