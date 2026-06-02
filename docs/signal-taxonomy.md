# Signal taxonomy — Ehrenthal et al. (2026) four-signal scheme (v0.4.0)

This document is the **thesis-citable reference** for the signal classification used by both MAS systems. The canonical source — what the agents actually read at runtime, what `/api/meta` serves on the public site, and what the dashboard renders — lives in [`systems/masfactory/masfactory_system/classification/schema.yaml`](../systems/masfactory/masfactory_system/classification/schema.yaml). This file explains the choices behind it.

---

## Primary source

> **Ehrenthal, J. C. F., Gonzalez-Padron, T. & Gruen, T. (2026).**
> *Global Strategic Marketing When Performance Is Noncommensurable: How Quantum-Computing Vendors Articulate Global Positions Through Nontechnical Signals.*

The paper studies the 2025 corporate-communications corpus of six quantum-computing vendors (D-Wave, Infleqtion, IonQ, Pasqal, Rigetti, Xanadu) using Atlas.ti-coded content analysis. The premise: when performance is noncommensurable (no shared benchmark — Tomesh et al. 2022 SupermarQ), actors articulate position through **observable nontechnical signals**, and the paper's coding scheme maps those signals into a four-category structure with named sub-markers per category.

Our v0.4.0 schema adopts that structure verbatim for the sub-markers it shares, with two explicit extensions (flagged `extension: true` in the YAML) needed for the Swiss public-sector slice of the ecosystem that Ehrenthal's vendor-only dataset doesn't cover.

---

## The four signal types

| Key | Label | Description |
|---|---|---|
| `legitimacy` | Legitimacy signals | Organisational and scientific credibility — who you are, what you've published, who you employ, what awards you've won. The base layer of credibility in a noncommensurable market. |
| `customer_cocreation` | Customer co-creation signals | Engagement with named customers and applications — collaborations, pilots, training. Demonstrate global relevance and early-adopter engagement rather than market penetration. |
| `community_ecosystem` | Community-ecosystem signals | Cloud-platform listings, HPC collaborations, industry/academic partnerships. The primary channels through which vendors depict global reach. |
| `future_trajectory` | Future-trajectory signals | Roadmaps, milestone sequences, technological-advance announcements, long-horizon claims. Stabilise expectations in early commercialisation. |

The paper's exact phrasing ("legitimacy, customer co-creation, community / ecosystem, and future trajectories") is preserved in our `signal_types[].label` and `signal_types[].grounding` fields so the live site cites the paper verbatim.

---

## 19 sub-categories (dimensions)

Every `signals` row in Supabase belongs to **exactly one dimension**, which in turn belongs to **exactly one signal type**. Per-dimension `weight`, `signal_cost`, and `observability` axes are layered on each (full table in `schema.yaml`).

### Legitimacy (8)

| Dimension key | Ehrenthal % | Sub-marker description |
|---|---|---|
| `leadership_expertise` | 14% | Named senior hires, scientific advisors, board appointments |
| `patents` | 12% | Patent filings (Swissreg / EPO / WIPO) |
| `publications` | 7% | Peer-reviewed papers, pre-prints, datasets |
| `awards` | 19% | Industry awards, prizes, formal recognitions |
| `testimonials` | 18% | Customer/partner endorsements, named reference quotes |
| `educational_outreach` | 16% | Workshops, MOOCs, student outreach, hackathons |
| `funding_event` *(extension)* | — | Funding rounds, SNF/Innosuisse/Horizon grants, government contracts |
| `regulatory_recognition` *(extension)* | — | National strategy publications, standards, export-control, certifications |

### Customer co-creation (3)

| Dimension key | Ehrenthal % | Sub-marker description |
|---|---|---|
| `collaborations_applications` | 85% | National/international collaborations targeting specific applications |
| `pilots_pocs` | 14% | Simulations, pilots, proofs of concept with named customers |
| `customer_training` | 3% | Customer enablement, training, developer relations |

### Community-ecosystem (4)

| Dimension key | Ehrenthal % | Sub-marker description |
|---|---|---|
| `cloud_platform_listings` | 43% | Availability on AWS Braket / Azure Quantum / IBM Quantum / etc. |
| `hpc_collaborations` | 32% | HPC-centre integrations, supercomputer collaborations |
| `industry_partnerships` | 14% | MoUs with industry, distribution agreements, ecosystem memberships |
| `academic_partnerships` | 10% | University joint labs, visiting professorships, research consortia |

### Future-trajectory (4)

| Dimension key | Ehrenthal % | Sub-marker description |
|---|---|---|
| `roadmaps` | 76% | Public product / technology roadmaps with named dates |
| `milestones` | 20% | Specific milestone announcements (X qubits by Y) |
| `technological_advances` | 11% | Qubit counts, gate fidelity, coherence, architectures, toolchain releases |
| `long_horizon_claims` | 4% | Fault-tolerant visions, broad future-state narratives |

The `%` column shows the share of within-category mentions reported in Ehrenthal et al. (2026, §Findings) for their 2025 vendor-comms dataset. We surface these in the on-site Methodology page so users can compare our Swiss-ecosystem distribution against the paper's global vendor distribution.

---

## Extensions to Ehrenthal's coding scheme

Two dimensions are **extensions** rather than verbatim sub-markers from the paper. The YAML flags them with `extension: true` and the website renders them with a small "ext." marker so the thesis can A/B with Ehrenthal's exact taxonomy if needed.

### `funding_event` (legitimacy)

Funding events sit in Ehrenthal's separate **Communication Categories** axis (Investor / Funding) rather than the four-signal scheme directly. In the wider signalling-theory literature, however, capital commitment by a third party is the canonical *costly* legitimacy signal:

- **Suchman (1995)** — pragmatic legitimacy rests on costly, verifiable commitments by external stakeholders.
- **Rieger, Dreller & Engelen (2025)** — show empirically that costly early-stage trademark filings predict VC funding outcomes; funding itself is the strongest "downstream" costly signal.

Treating funding as a legitimacy signal preserves the scheme's interpretability for Swiss public-sector actors (SQI / SNF / Innosuisse grants) whose primary visible legitimacy signal *is* a funding event.

### `regulatory_recognition` (legitimacy)

Not in Ehrenthal's coded markers — they study vendor-authored corporate communications, where regulatory recognition is rare. But Swiss public infrastructure actors (SQI, NCCR, SNF, ETH-domain RIs, Innosuisse) routinely produce regulatory-recognition signals: federal quantum-strategy publications, standards-body participation, export-control inclusion, certification milestones. Grounded in Suchman (1995) cognitive legitimacy — categorical recognition by the state.

Both extensions are intentionally narrow: they extend coverage without inflating the schema. The thesis can drop them at evaluation time to reproduce a strictly Ehrenthal-compliant analysis if needed.

---

## Signal cost (credibility) and observability (receiver condition)

Each dimension carries two additional axes — **layered on top of** the Ehrenthal scheme rather than replacing any part of it. Both are anchored in the wider signalling-theory literature the paper builds on (Connelly et al. 2011 review):

- **`signal_cost`** ∈ {high, medium, low} — Spence (1973) credibility axis. A signal is informative to the extent it is costly or hard to fake. Used by `scoring.py` to credibility-discount low-cost signals (multipliers: high=1.0, medium=0.7, low=0.4).
- **`observability`** ∈ {high, medium, low} — Connelly et al. (2011) receiver condition. A signal must be publicly verifiable to function. Used to flag signals that are present in the agents' run but may be hard for an external receiver to verify.

The schema's per-dimension `weight` is the **base impact weight**; the `cost_multiplier × weight` product is what feeds the credibility-weighted impact score on the dashboard.

---

## v0.3.0 → v0.4.0 legacy mapping

The migration in [`systems/masfactory/masfactory_system/persistence/schema.sql`](../systems/masfactory/masfactory_system/persistence/schema.sql) is canonical and idempotent. Every legacy v0.3.0 dimension key rewrites to exactly one v0.4.0 key (deterministic, no Classifier re-run needed):

| v0.3.0 key (legacy) | v0.4.0 key (new) | v0.4.0 signal_type |
|---|---|---|
| `technical_capability` | `technological_advances` | `future_trajectory` |
| `research_output` | `publications` | `legitimacy` |
| `ip_filing` | `patents` | `legitimacy` |
| `infrastructure_or_facility` | `hpc_collaborations` | `community_ecosystem` |
| `partnership_or_alliance` | `industry_partnerships` | `community_ecosystem` |
| `funding_or_grant` | `funding_event` | `legitimacy` |
| `hiring_or_talent` | `leadership_expertise` | `legitimacy` |
| `regulatory_or_policy` | `regulatory_recognition` | `legitimacy` |
| `market_positioning` | `roadmaps` | `future_trajectory` |

The original v0.3.0 value is preserved on every row in `signals.dimension_legacy`, so a pre-migration analysis (e.g. "how did the dashboard look the day before the rename?") is still reproducible from Supabase directly. The label layer in `systems/api/api_app/labels.py` exposes `LEGACY_DIMENSION_MAP` + `normalise_dimension()` so any code path receiving a legacy key transparently resolves to the v0.4.0 label.

---

## How the agents use this

Both systems' Classifier nodes load `schema.yaml` at start-up via `classification.load_schema()` and render it into the prompt via `schema_as_prompt_block()`. The prompt now groups dimensions by `signal_type` so the LLM reasons at the four-signal level first:

```
== signal_type: legitimacy (Legitimacy) ==
  - leadership_expertise (non-technical, cost=medium): Named senior hires...
  - patents (technical, cost=high): Patent filings...
  ...
== signal_type: customer_cocreation (Customer co-creation) ==
  - collaborations_applications (non-technical, cost=medium): ...
  ...
```

The Classifier output schema requires BOTH `signal_type` and `dimension`. The Persistence step normalises any stray legacy emit via `normalise_dimension()` before insert.

---

## References

| Paper | Used for |
|---|---|
| Ehrenthal, Gonzalez-Padron & Gruen (2026) | Four-signal scheme + sub-markers; the primary frame |
| Suchman (1995) | Receiver-side legitimacy; cognitive-legitimacy framing for `regulatory_recognition` |
| Spence (1973) | Signal-cost credibility mechanism |
| Connelly et al. (2011) | Signalling theory review; receiver condition (observability axis) |
| Rieger, Dreller & Engelen (2025) | Costly trademark/patent signals predict VC funding (justifies `funding_event` as legitimacy) |
| Knight & Cavusgil (2004) | Capability-based competitive advantage (research output as costly capability evidence) |
| Hilkamo & Granqvist (2022) | Sense-making in de novo quantum markets (justifies leadership-expertise weighting) |
| Tomesh et al. (2022) — SupermarQ | No unified quantum benchmark exists (premise for the "noncommensurable" framing) |
| Adner (2017) | Ecosystem as structure (community-ecosystem signal type) |
| Mohr & Sarin (2009) | High-technology marketing strategy (anchors customer-co-creation framing) |
| Kolbe & Burnett (1991) | Content-analysis methodology (Ehrenthal's coding-procedure source) |
| Blomqvist et al. (2008) | Collaborative networks as legitimacy signal |
| Song, Zhao & Wei (2025) | Coattail legitimacy (industry-partnership grounding) |
| Robinson & Veresiu (2025) | Legitimacy timing |

Every reference also appears on the live Methodology page at [/methodology](https://mas-deeptech-research.cloud/methodology) — served from the same YAML.
