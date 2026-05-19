"""Extractor — turns raw documents into candidate signals.

Agent: the work is "read this text, decide what counts as a signal, quote it"
which is exactly the kind of judgement LLMs are reasonable at.
"""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter


EXTRACTOR_INSTRUCTIONS = """You are the Extractor in a Swiss-quantum ecosystem-mapping pipeline.

Given a JSON array of raw documents (each with `actor_slug`, `source_kind`,
`source_url`, `title`, `text`), produce a JSON array of *signal candidates*.

A signal candidate is anything from the document that could plausibly affect
how an external observer reads the actor's position: a new capability, a
partnership, a hire, a paper, a grant, a press claim.

Rules:
- Do NOT classify — the next agent handles that. Just surface candidates.
- Each candidate MUST include a short `evidence_quote` lifted verbatim from
  the source text. If no quote can be found, drop the candidate.
- Skip generic boilerplate ("we are a leading provider of ...").
- Aim for at most 3 candidates per document.
- Return ONLY JSON, no prose.
"""

EXTRACTOR_PROMPT = """<documents>{documents_json}</documents>

Return JSON of shape:
{{
  "candidates": [
    {{
      "actor_slug": "...",
      "source_kind": "...",
      "source_url": "...",
      "title": "...",
      "summary": "...",
      "evidence_quote": "..."
    }}
  ]
}}
"""


ExtractorNode = NodeTemplate(
    Agent,
    instructions=EXTRACTOR_INSTRUCTIONS,
    prompt_template=EXTRACTOR_PROMPT,
    pull_keys={"documents_json": "JSON array of raw Document objects"},
    push_keys={"candidates_json": "JSON object with `candidates` array of SignalCandidate"},
    formatters=[ParagraphMessageFormatter(), TaggedFieldMessageFormatter()],
)
