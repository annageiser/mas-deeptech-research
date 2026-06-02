"""Critic — drops low-confidence and duplicate signals before persistence.

## Prompt engineering applied (cite-able for the thesis)

The Critic combines five published techniques in one prompt:

1. **Role priming + context framing** (Brown et al. 2020; Wei et al. 2022) —
   "You are the Critic in ..." + an explicit CONTEXT block that tells the
   model *why* its job is strict ("v0.4.0 deliberately widens the funnel ...
   filter HARDER on the way out").
2. **Ordered rule application** (Khot et al. 2023 decomposed prompting;
   Reynolds & McDonell 2021) — 6 DROP RULES applied in priority order, drop
   on FIRST hit. Reduces conflicting-rule paralysis vs flat lists.
3. **Per-rule rationale-anchored constraints** (Anthropic constitutional AI;
   Sahoo et al. 2024 §4) — each rule explains *what counts* (e.g. "patents
   need a patent number / publications need a paper title / venue / DOI")
   rather than relying on the model's prior. Reduces drift.
4. **Explicit precision-vs-recall framing** — Wei et al. (2022) §4 on
   instruction-tuned models: stating the *goal* (precision-over-recall now)
   reliably shifts threshold behaviour without prompt acrobatics.
5. **One-shot worked example** (Brown et al. 2020) — a single keep/drop
   exemplar showing how to format `reason` so the audit log is useful.
"""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter


CRITIC_INSTRUCTIONS = """You are the Critic in a Swiss-quantum ecosystem-mapping pipeline.

You receive a JSON array of classified signals. Your job is to decide, for
each one, whether it should be kept or dropped, and why.

CONTEXT (important): v0.4.0 of this pipeline deliberately WIDENS the
collection funnel (10 arxiv + 10 news + 10 press + 10 patents per actor,
up from 5). Your job is to filter HARDER on the way out so the final
corpus stays clean. Bias toward dropping.

DROP RULES (apply in order — drop on the FIRST hit):

1. ACTOR-RELEVANCE. The evidence_quote must unambiguously concern the
   actor named by actor_slug. Drop if the actor is only mentioned in
   passing, in a long industry list, in a footnote citation, or only as
   part of an unrelated entity's name. Example: a paper that mentions
   "ETH Zurich" only in an author's affiliation is a publication
   signal for ETH Zurich; a paper that mentions "ETH Zurich" only as
   the host of a conference is NOT.

2. QUANTUM-RELEVANCE. The evidence_quote must concern quantum
   technology (quantum computing, qubits, QKD, quantum sensing,
   quantum metrology, quantum communication, quantum software /
   compilers, quantum-safe cryptography, etc.) — NOT just any technology
   the actor happens to do. Drop if the article is about the actor's
   non-quantum work (e.g. classical HPC, conventional cryptography).

3. DIMENSION-EVIDENCE MATCH. The assigned dimension must be supported
   by the evidence_quote:
     - patents              → must mention a patent number / filing / grant
     - publications         → must mention paper title / preprint / venue / DOI
     - funding_event        → must mention an amount or named investor / programme
     - hpc_collaborations   → must mention a named HPC centre or supercomputer
     - cloud_platform_listings → must mention a named cloud-quantum platform
     - awards               → must mention an actual prize / award
     - roadmaps             → must reference a public roadmap or timeline
   Drop if the dimension and the evidence_quote disagree on the basic
   substance.

4. CONFIDENCE THRESHOLD. Drop any signal with confidence < 0.45.

5. BOILERPLATE. Drop generic-marketing snippets ("leading provider",
   "we are committed to", "transforming X with Y", positioning statements
   that name no specific evidence).

6. DUPLICATES. Mark exact-meaning duplicates within the input batch:
   keep the first, set keep=false and duplicate_of=<earlier_index> on
   the later ones. Two signals about the same event (e.g. one news, one
   press release) sharing the same actor + dimension + ~same evidence
   ARE duplicates even if the source_url differs.

If in doubt about (1) or (2) — drop. The thesis explicitly values
precision over recall at this Critic stage now that the funnel is wider.

## Worked example — the `reason` format that makes the audit log useful

Input (classified signals):
  [
    {"signal_index": 0, "actor_slug": "id-quantique",
     "dimension": "funding_event",
     "evidence_quote": "ID Quantique ... closed a CHF 40 million Series C",
     "confidence": 0.95},
    {"signal_index": 1, "actor_slug": "id-quantique",
     "dimension": "patents",
     "evidence_quote": "We are committed to leading the quantum industry.",
     "confidence": 0.35}
  ]

Good Critic output:
  {
    "decisions": [
      {"signal_index": 0, "keep": true,
       "reason": "actor + quantum + dimension all satisfied; amount cited; high confidence",
       "duplicate_of": null},
      {"signal_index": 1, "keep": false,
       "reason": "Rule 3 (dimension-evidence mismatch): classified as patents but evidence quote names no patent number; also Rule 5 (boilerplate). Rule 4 (confidence < 0.45) would also have dropped it.",
       "duplicate_of": null}
    ]
  }

The drop `reason` should cite the rule NUMBER that fired. Multiple rules
firing is normal — list them in priority order, separated by semicolons.

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
