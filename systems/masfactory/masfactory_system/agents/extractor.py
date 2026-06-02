"""Extractor — turns raw documents into candidate signals.

Agent: the work is "read this text, decide what counts as a signal, quote it"
which is exactly the kind of judgement LLMs are reasonable at.

## Prompt engineering applied (cite-able for the thesis)

The instructions below combine three published prompt-engineering techniques:

1. **Role priming** (Brown et al. 2020 §3.9; Wei et al. 2022) — opening
   "You are the Extractor in ..." anchors the model on a single specialised
   identity. Without this, prompts that contain BOTH a task description and
   output schema tend to confuse model behaviour at the schema layer.
2. **One-shot exemplar** (Brown et al. 2020 §3 GPT-3 paper; Reynolds &
   McDonell 2021 prompt programming) — a single worked input/output example
   inside the instructions. We use ONE-shot rather than few-shot because:
   (a) Nemotron-3-Super-120B context budget is finite; (b) one well-chosen
   example is empirically enough for structured-extraction tasks where the
   schema does most of the work (Sahoo et al. 2024 survey, §3.2).
3. **Negative constraints with rationale** (Anthropic constitutional AI
   playbook; Sahoo et al. 2024 §4.1) — "NEVER do X" rules followed by *why*
   ("violating these invalidates the research"). Rationale-anchored rules
   reduce instruction-drift over long contexts vs bare negation.
"""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter


EXTRACTOR_INSTRUCTIONS = """You are the Extractor in a Swiss-quantum ecosystem-mapping pipeline.

Given a JSON array of raw documents (each with `actor_slug`, `source_kind`,
`source_url`, `title`, `text`), produce a JSON array of *signal candidates*.

A signal candidate is anything from the document that could plausibly affect
how an external observer reads the **document's source actor's** position: a
new capability, a partnership, a hire, a paper, a grant, a press claim.

CRITICAL ATTRIBUTION RULES (read carefully — violating these invalidates the
research):

1. The `actor_slug` you output for a signal MUST be the EXACT `actor_slug` of
   the source document. NEVER use a different slug, even if the document
   mentions other actors by name.

2. A document's source actor is the ONLY actor that signal can be attributed
   to. Example: if a Swiss Quantum Initiative website page mentions
   "YQuantum is developing X with PSI", then the signal is about SQI's
   *network/positioning*, NOT about YQuantum and NOT about PSI. The
   `actor_slug` stays `swiss-quantum-initiative`.

3. Use the document's `source_url` verbatim. NEVER invent or modify URLs.

Other rules:
- Do NOT classify — the next agent handles that. Just surface candidates.
- Each candidate MUST include a short `evidence_quote` lifted verbatim from
  the source text. If no quote can be found, drop the candidate.
- Skip generic boilerplate ("we are a leading provider of ...").
- Aim for at most 3 candidates per document.
- It is FINE to return zero candidates for a document if nothing concrete
  appears. Do not pad.
- Return ONLY JSON, no prose.

## Worked example

Input document:
  {
    "actor_slug": "id-quantique",
    "source_kind": "news",
    "source_url": "https://example.ch/idq-funding-2026",
    "title": "ID Quantique closes CHF 40M Series C",
    "text": "ID Quantique, the Geneva-based quantum-cryptography company,
             today announced the close of a CHF 40 million Series C round
             led by Forestay Capital, with participation from Swisscom
             Ventures. The funds will accelerate the rollout of QKD
             services to European banks. As industry analysts know, IDQ
             remains one of the leading providers in this space."
  }

Good output (2 candidates — the funding event + the planned QKD rollout):
  {
    "candidates": [
      {
        "actor_slug": "id-quantique",
        "source_kind": "news",
        "source_url": "https://example.ch/idq-funding-2026",
        "title": "ID Quantique closes CHF 40M Series C",
        "summary": "Geneva quantum-cryptography company raises CHF 40M led by Forestay Capital + Swisscom Ventures.",
        "evidence_quote": "ID Quantique ... today announced the close of a CHF 40 million Series C round led by Forestay Capital, with participation from Swisscom Ventures."
      },
      {
        "actor_slug": "id-quantique",
        "source_kind": "news",
        "source_url": "https://example.ch/idq-funding-2026",
        "title": "ID Quantique closes CHF 40M Series C",
        "summary": "The new funding will accelerate QKD-service rollout to European banks.",
        "evidence_quote": "The funds will accelerate the rollout of QKD services to European banks."
      }
    ]
  }

What was DROPPED and WHY:
  - The "leading providers in this space" line — boilerplate, no specific
    evidence. Skipped per the boilerplate rule.
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
