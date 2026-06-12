"""Human-readable labels + the signalling-theory cost/observability axes.

v0.4.0 — aligned with Ehrenthal, Gonzalez-Padron & Gruen (2026)'s four-signal
scheme: legitimacy / customer_cocreation / community_ecosystem / future_trajectory.
The 18 dimension keys are Ehrenthal's coded markers (16 verbatim + 2 extensions:
funding_event, regulatory_recognition, both grounded in Suchman 1995 + Rieger
et al. 2025).

Vendored copy (the API container doesn't bundle the masfactory package).
CANONICAL SOURCE for weights / costs / observability:
systems/masfactory/masfactory_system/classification/schema.yaml — keep in sync.

Legacy v0.3.0 dimension keys map onto v0.4.0 keys via LEGACY_DIMENSION_MAP
below; lookups normalise via normalise_dimension() so the API stays
resilient against any not-yet-migrated rows.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# v0.3.0 → v0.4.0 dimension migration (canonical mapping; mirrors
# classification.legacy_dimension_map() in the masfactory package).
# ---------------------------------------------------------------------------

LEGACY_DIMENSION_MAP = {
    "technical_capability":       "technological_advances",
    "research_output":            "publications",
    "ip_filing":                  "patents",
    "infrastructure_or_facility": "hpc_collaborations",
    "partnership_or_alliance":    "industry_partnerships",
    "funding_or_grant":           "funding_event",
    "hiring_or_talent":           "leadership_expertise",
    "regulatory_or_policy":       "regulatory_recognition",
    "market_positioning":         "roadmaps",
}


def normalise_dimension(key: str) -> str:
    """Pass-through for v0.4.0; remap for v0.3.0; pass-through for unknowns."""
    if not key:
        return key
    if key in DIMENSION_LABEL:
        return key
    return LEGACY_DIMENSION_MAP.get(key, key)


# ---------------------------------------------------------------------------
# Top-level signal types (Ehrenthal four-signal scheme)
# ---------------------------------------------------------------------------

# v0.4.19: defense_signals is no longer a signal_type — it's two boolean
# flags (defense_engagement + defense_ambivalence) overlaid on the
# Ehrenthal four. See docs/migrations.md § v0.4.19. defense_signals is
# kept in the LEGACY map below so pre-migration rows still render with
# a clear label until the SQL backfill is applied.
SIGNAL_TYPE_LABEL = {
    "legitimacy":          "Legitimacy signals",
    "customer_cocreation": "Customer co-creation signals",
    "community_ecosystem": "Community-ecosystem signals",
    "future_trajectory":   "Future-trajectory signals",
}

SIGNAL_TYPE_SHORT = {
    "legitimacy":          "Legitimacy",
    "customer_cocreation": "Customer co-creation",
    "community_ecosystem": "Community / ecosystem",
    "future_trajectory":   "Future trajectory",
}

# Pre-v0.4.19 values that may still exist in old rows. Bug 3 fix: the
# label resolver falls back to this map, then a generic "(legacy: <key>)"
# message — so a row never renders without a label.
LEGACY_SIGNAL_TYPE_LABEL = {
    "defense_signals":     "Defense / national-security (pre-v0.4.19)",
}

# v0.4.19 boolean-flag labels. Used by the UI to render badges on top of
# the signal_type pill.
SIGNAL_FLAG_LABEL = {
    "defense_engagement":  "Defense engagement",
    "defense_ambivalence": "Defense ambivalence (info withheld)",
}

SIGNAL_TYPE_DESCRIPTION = {
    "legitimacy":
        "Who you are + what you've published. Leadership / board expertise, "
        "patents, publications, awards, testimonials, educational outreach, "
        "funding events, regulatory recognition.",
    "customer_cocreation":
        "Engagement with named customers and applications. Collaborations for "
        "applications, pilots / proofs of concept, customer training.",
    "community_ecosystem":
        "Where you sit in the wider quantum stack. Cloud-platform listings, "
        "HPC collaborations, industry partnerships, academic partnerships.",
    "future_trajectory":
        "Where you're going. Roadmaps, milestone sequences, technological-"
        "advance announcements, long-horizon claims.",
}

SIGNAL_TYPE_COLOR = {
    "legitimacy":          "#1f77b4",   # blue
    "customer_cocreation": "#2ca02c",   # green
    "community_ecosystem": "#9467bd",   # purple
    "future_trajectory":   "#ff7f0e",   # orange
}

# v0.4.19 flag colours — used as badge backgrounds in the UI.
SIGNAL_FLAG_COLOR = {
    "defense_engagement":  "#8c564b",   # brown (gravity)
    "defense_ambivalence": "#7f7f7f",   # grey  (withheld)
}

# Legacy colour fallback so pre-migration rows still render distinguishably.
LEGACY_SIGNAL_TYPE_COLOR = {
    "defense_signals":     "#8c564b",   # brown — same as defense_engagement now
}


# ---------------------------------------------------------------------------
# Dimensions (Ehrenthal sub-categories — 18 keys)
# ---------------------------------------------------------------------------

DIMENSION_LABEL = {
    # Legitimacy
    "leadership_expertise":        "Leadership / board expertise",
    "patents":                     "Patents",
    "publications":                "Publications",
    "awards":                      "Awards",
    "testimonials":                "Testimonials",
    "educational_outreach":        "Educational outreach",
    "funding_event":               "Funding event",
    "regulatory_recognition":      "Regulatory recognition",
    # Customer co-creation
    "collaborations_applications": "Collaborations for applications",
    "pilots_pocs":                 "Pilots & POCs",
    "customer_training":           "Customer training",
    # Community-ecosystem
    "cloud_platform_listings":     "Cloud-platform listings",
    "hpc_collaborations":          "HPC collaborations",
    "industry_partnerships":       "Industry partnerships",
    "academic_partnerships":       "Academic partnerships",
    # Future-trajectory
    "roadmaps":                    "Roadmaps",
    "milestones":                  "Milestones",
    "technological_advances":      "Technological advances",
    "long_horizon_claims":         "Long-horizon claims",
    # Defense (v0.4.2)
    "defense_engagement":          "Defense engagement",
    "defense_ambivalence":         "Defense ambivalence",
}

DIMENSION_HINT = {
    "leadership_expertise":        "Named senior hires, scientific advisors, board appointments.",
    "patents":                     "Patent filings, design rights, trademarks (Swissreg / EPO / WIPO).",
    "publications":                "Peer-reviewed papers, pre-prints, datasets.",
    "awards":                      "Industry awards, prizes, formal recognitions.",
    "testimonials":                "Customer / partner endorsements, named reference quotes.",
    "educational_outreach":        "Workshops, MOOCs, student outreach, hackathons.",
    "funding_event":               "Funding rounds, SNF/Innosuisse/Horizon grants, government contracts.",
    "regulatory_recognition":      "Strategy publications, standards, export-control, certifications.",
    "collaborations_applications": "Named collaborations targeting specific applications.",
    "pilots_pocs":                 "Simulations, pilots, proofs of concept with named customers.",
    "customer_training":           "Customer enablement, training, developer relations.",
    "cloud_platform_listings":     "Availability on AWS Braket / Azure Quantum / IBM Quantum / etc.",
    "hpc_collaborations":          "HPC-centre integrations, supercomputer collaborations.",
    "industry_partnerships":       "MoUs with industry, distribution agreements, ecosystem memberships.",
    "academic_partnerships":       "University joint labs, visiting professorships, research consortia.",
    "roadmaps":                    "Public product / technology roadmaps with named dates.",
    "milestones":                  "Specific milestone announcements (X qubits by Y).",
    "technological_advances":      "Qubit counts, gate fidelity, coherence, architectures, toolchain.",
    "long_horizon_claims":         "Fault-tolerant visions, broad future-state narratives.",
}

# Legacy capability/legitimacy CHANNEL membership (kept for v0.3.0 dashboards)
# is now derived per-dimension from schema.yaml's `channel:` field rather than
# enumerated here; the two sets below are computed at module-load time as
# fallbacks if a dimension shows up that the channel map doesn't cover.
CAPABILITY_DIMENSIONS = {
    "patents",
    "publications",
    "hpc_collaborations",
    "pilots_pocs",
    "milestones",
    "technological_advances",
}
LEGITIMACY_DIMENSIONS = set(DIMENSION_LABEL) - CAPABILITY_DIMENSIONS


DIMENSION_WEIGHT = {
    "leadership_expertise":        0.9,
    "patents":                     1.4,
    "publications":                1.0,
    "awards":                      0.8,
    "testimonials":                0.5,
    "educational_outreach":        0.6,
    "funding_event":               1.5,
    "regulatory_recognition":      0.7,
    "collaborations_applications": 1.1,
    "pilots_pocs":                 1.0,
    "customer_training":           0.7,
    "cloud_platform_listings":     0.9,
    "hpc_collaborations":          1.0,
    "industry_partnerships":       0.9,
    "academic_partnerships":       0.9,
    "roadmaps":                    0.5,
    "milestones":                  0.7,
    "technological_advances":      1.0,
    "long_horizon_claims":         0.3,
    "defense_engagement":          1.3,
    "defense_ambivalence":         0.4,
}

# Signal-cost class per dimension — heart of signalling theory (Spence 1973).
DIMENSION_COST = {
    "leadership_expertise":        "medium",
    "patents":                     "high",
    "publications":                "high",
    "awards":                      "medium",
    "testimonials":                "low",
    "educational_outreach":        "medium",
    "funding_event":               "high",
    "regulatory_recognition":      "medium",
    "collaborations_applications": "medium",
    "pilots_pocs":                 "medium",
    "customer_training":           "low",
    "cloud_platform_listings":     "medium",
    "hpc_collaborations":          "high",
    "industry_partnerships":       "medium",
    "academic_partnerships":       "medium",
    "roadmaps":                    "low",
    "milestones":                  "medium",
    "technological_advances":      "medium",
    "long_horizon_claims":         "low",
    "defense_engagement":          "high",
    "defense_ambivalence":         "low",
}

COST_MULTIPLIER = {"high": 1.0, "medium": 0.7, "low": 0.4}

DIMENSION_OBSERVABILITY = {
    "leadership_expertise":        "high",
    "patents":                     "high",
    "publications":                "high",
    "awards":                      "high",
    "testimonials":                "high",
    "educational_outreach":        "high",
    "funding_event":               "high",
    "regulatory_recognition":      "high",
    "collaborations_applications": "high",
    "pilots_pocs":                 "high",
    "customer_training":           "high",
    "cloud_platform_listings":     "high",
    "hpc_collaborations":          "medium",
    "industry_partnerships":       "high",
    "academic_partnerships":       "high",
    "roadmaps":                    "high",
    "milestones":                  "high",
    "technological_advances":      "medium",
    "long_horizon_claims":         "high",
    "defense_engagement":          "high",
    "defense_ambivalence":         "medium",
}

# Dimension → signal_type lookup, computed inline (keeps the source of truth
# in one place — modifying DIMENSION_LABEL automatically affects this).
DIMENSION_SIGNAL_TYPE = {
    "leadership_expertise":        "legitimacy",
    "patents":                     "legitimacy",
    "publications":                "legitimacy",
    "awards":                      "legitimacy",
    "testimonials":                "legitimacy",
    "educational_outreach":        "legitimacy",
    "funding_event":               "legitimacy",
    "regulatory_recognition":      "legitimacy",
    "collaborations_applications": "customer_cocreation",
    "pilots_pocs":                 "customer_cocreation",
    "customer_training":           "customer_cocreation",
    "cloud_platform_listings":     "community_ecosystem",
    "hpc_collaborations":          "community_ecosystem",
    "industry_partnerships":       "community_ecosystem",
    "academic_partnerships":       "community_ecosystem",
    "roadmaps":                    "future_trajectory",
    "milestones":                  "future_trajectory",
    "technological_advances":      "future_trajectory",
    "long_horizon_claims":         "future_trajectory",
    "defense_engagement":          "defense_signals",
    "defense_ambivalence":         "defense_signals",
}

COST_LABEL = {"high": "High-cost (hard to fake)", "medium": "Medium-cost", "low": "Low-cost (cheap talk)"}


def cost_class(dimension_key: str) -> str:
    return DIMENSION_COST.get(normalise_dimension(dimension_key), "medium")

def cost_multiplier(dimension_key: str) -> float:
    return COST_MULTIPLIER.get(cost_class(dimension_key), 0.7)

def cost_label(dimension_key: str) -> str:
    return COST_LABEL.get(cost_class(dimension_key), "Medium-cost")


def signal_type_for(dimension_key: str) -> str:
    """Return the Ehrenthal signal_type for a given dimension key. Accepts
    v0.3.0 or v0.4.0 keys."""
    return DIMENSION_SIGNAL_TYPE.get(normalise_dimension(dimension_key), "")


def signal_type_label(key: str) -> str:
    """v0.4.19 (Bug 3 fix): resolve a label for any signal_type value.

    Resolution order:
      1. Current v0.4.19 4-value map
      2. Legacy pre-v0.4.19 map (defense_signals etc.)
      3. Title-cased fallback with a "(legacy)" annotation so it's
         visibly different from a current label.
    """
    if not key:
        return "(legacy: unknown)"
    if key in SIGNAL_TYPE_LABEL:
        return SIGNAL_TYPE_LABEL[key]
    if key in LEGACY_SIGNAL_TYPE_LABEL:
        return LEGACY_SIGNAL_TYPE_LABEL[key]
    return f"(legacy: {key.replace('_', ' ')})"


def signal_type_color(key: str) -> str:
    """Same fallback strategy for colour — grey if unknown."""
    return (
        SIGNAL_TYPE_COLOR.get(key)
        or LEGACY_SIGNAL_TYPE_COLOR.get(key)
        or "#999999"   # grey for legacy
    )


def signal_flag_label(key: str) -> str:
    """Label for a boolean flag (defense_engagement etc.)."""
    return SIGNAL_FLAG_LABEL.get(key, key.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Actor categories
# ---------------------------------------------------------------------------

CATEGORY_LABEL = {
    "national_initiative":         "National initiative",
    "university_or_research_hub":  "University / research hub",
    "ecosystem_builder":           "Ecosystem builder",
    "private_company":             "Private company",
    "government":                  "Government",
}

CATEGORY_COLOR = {
    "national_initiative":         "#1f77b4",
    "university_or_research_hub":  "#2ca02c",
    "ecosystem_builder":           "#9467bd",
    "private_company":             "#ff7f0e",
    "government":                  "#8c564b",
}

SYSTEM_LABEL = {
    "masfactory": "System A · MASFactory",
    "hermes":     "System B · Hermes",
}
SYSTEM_SHORT = {"masfactory": "System A", "hermes": "System B"}

SOURCE_KIND_LABEL = {
    "arxiv":    "arXiv paper",
    "website":  "Actor website",
    "news":     "News article",
    "swissreg": "Swissreg patent",
    "manual":   "Manual entry",
}


def dimension(key: str) -> str:
    """Display label for a dimension key. Accepts v0.3.0 (auto-migrates) or v0.4.0."""
    return DIMENSION_LABEL.get(normalise_dimension(key), key.replace("_", " ").title())

def category(key: str) -> str:
    return CATEGORY_LABEL.get(key, key.replace("_", " ").title())

def system_label(key: str) -> str:
    return SYSTEM_LABEL.get(key, key)

def system_short_label(key: str) -> str:
    return SYSTEM_SHORT.get(key, key)

def source_kind(key: str) -> str:
    return SOURCE_KIND_LABEL.get(key, key.title())

def tech_label(is_technical: bool) -> str:
    return "Capability" if is_technical else "Legitimacy"
