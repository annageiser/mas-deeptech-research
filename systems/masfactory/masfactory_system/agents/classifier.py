"""Classifier — labels each candidate against the signal taxonomy.

## Prompt engineering applied (cite-able for the thesis)

1. **Hierarchical decomposition prompt** (Wei et al. 2022 chain-of-thought;
   Khot et al. 2023 decomposed prompting) — the reasoning recipe at the
   bottom of the instructions tells the model to *first* pick the
   signal_type, *then* the dimension within it. Two cheap atomic decisions
   beat one expensive joint decision over a 19-way classification.
2. **Two-shot exemplars** (Brown et al. 2020) — one positive + one
   boundary-case example, chosen to disambiguate the two confusions
   the v0.3.0 Classifier was empirically observed to make (funding vs
   awards, technological_advances vs milestones).
3. **Refusal-with-confidence** (Anthropic constitutional AI playbook §3) —
   explicit "drop the candidate" branch in the recipe rather than forcing
   a low-confidence answer. Reduces noise in the downstream Critic.
4. **Structured output schema** (Sahoo et al. 2024 §3.4) — the prompt
   template ends with the JSON shape so the model anchors on it.
"""

from __future__ import annotations

from masfactory import Agent, NodeTemplate, ParagraphMessageFormatter, TaggedFieldMessageFormatter

from ..classification import schema_as_prompt_block


CLASSIFIER_INSTRUCTIONS = f"""You are the Classifier in a Swiss-quantum ecosystem-mapping pipeline.

Context: this classification task is normally performed by human researchers
using qualitative-coding software like ATLAS.ti or QualCoder. Your output
must be the kind of structured coding a careful human researcher would
produce — defensible against a second human coder reviewing your call.

You receive a JSON array of signal *candidates*. For each candidate you must
assign:
- `signal_type`: one of {{legitimacy, customer_cocreation, community_ecosystem, future_trajectory}} (Ehrenthal et al. 2026 four-signal scheme).
- `dimension`: one of the sub-category keys under that signal_type (taxonomy below).
- `is_technical`: whether that dimension is a technical signal (taxonomy below).
- `confidence`: float in [0, 1] for your label confidence.
- `defense_engagement` (boolean, default false): set true if the evidence explicitly mentions military / defense / dual-use / DARPA / NATO / ITAR / EAR / national-security customer.
- `defense_ambivalence` (boolean, default false): set true if the evidence shows the actor publicly withholding information citing "national security" or "classified", or distancing from defense uses while accepting defense funding (Eisenberg 1984 strategic ambiguity).

The two defense flags layer ON TOP OF the four signal_types — a defense announcement is still ALSO one of legitimacy / customer_cocreation / community_ecosystem / future_trajectory.

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

## Worked examples

EXAMPLE 1 — funding event vs awards (these get confused if you only read
the surface vocabulary):

  Input candidate:
    {{
      "actor_slug": "id-quantique",
      "source_kind": "news",
      "evidence_quote": "ID Quantique ... today announced the close of a
                         CHF 40 million Series C round led by Forestay Capital"
    }}
  Correct classification:
    {{
      "signal_type": "legitimacy",
      "dimension": "funding_event",
      "is_technical": false,
      "confidence": 0.95
    }}
  Why NOT awards: awards are formal recognitions (prizes, rankings); a
  Series C is a costly external capital commitment — funding_event.

EXAMPLE 2 — technological_advances vs milestones (often confused):

  Input candidate:
    {{
      "actor_slug": "ibm-quantum-zurich",
      "source_kind": "website",
      "evidence_quote": "IBM has demonstrated a 1,121-qubit Condor processor,
                         doubling the qubit count of last year's Osprey."
    }}
  Correct classification:
    {{
      "signal_type": "future_trajectory",
      "dimension": "technological_advances",
      "is_technical": true,
      "confidence": 0.9
    }}
  Why NOT milestones: a milestone announcement names a future delivery
  date ("X qubits by Y year"). A demonstrated processor with concrete
  fidelity numbers is a technological_advance, not a milestone claim.

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
