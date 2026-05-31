"""Human-readable labels + the signalling-theory cost/observability axes.

Vendored copy (the API container doesn't bundle the masfactory package).
CANONICAL SOURCE for weights / costs / observability:
systems/masfactory/masfactory_system/classification/schema.yaml — keep in sync.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Signal-classification dimensions
# ---------------------------------------------------------------------------

DIMENSION_LABEL = {
    "technical_capability":    "Technical capability",
    "research_output":         "Research output",
    "ip_filing":               "IP & patents",
    "infrastructure_or_facility": "Infrastructure",
    "partnership_or_alliance": "Partnership",
    "funding_or_grant":        "Funding",
    "hiring_or_talent":        "Hiring & talent",
    "regulatory_or_policy":    "Regulatory & policy",
    "market_positioning":      "Market positioning",
}

DIMENSION_HINT = {
    "technical_capability":    "Qubits, gate fidelity, coherence, software releases.",
    "research_output":         "Peer-reviewed papers, pre-prints, datasets.",
    "ip_filing":               "Patents, design rights, trademark applications.",
    "infrastructure_or_facility": "New labs, cleanrooms, on-prem processors.",
    "partnership_or_alliance": "MoUs, joint labs, customer wins.",
    "funding_or_grant":        "Funding rounds, SNF/Innosuisse/Horizon grants.",
    "hiring_or_talent":        "Named leadership hires, advisors, drives.",
    "regulatory_or_policy":    "Strategy publications, standards, certifications.",
    "market_positioning":      "Roadmaps, keynotes, branding shifts.",
}

CAPABILITY_DIMENSIONS = {
    "technical_capability",
    "research_output",
    "ip_filing",
    "infrastructure_or_facility",
}
LEGITIMACY_DIMENSIONS = {
    "partnership_or_alliance",
    "funding_or_grant",
    "hiring_or_talent",
    "regulatory_or_policy",
    "market_positioning",
}

DIMENSION_WEIGHT = {
    "technical_capability":    1.3,
    "research_output":         1.0,
    "ip_filing":               1.4,
    "infrastructure_or_facility": 1.2,
    "partnership_or_alliance": 0.9,
    "funding_or_grant":        1.5,
    "hiring_or_talent":        0.8,
    "regulatory_or_policy":    0.7,
    "market_positioning":      0.4,
}

# Signal-cost class per dimension — heart of signalling theory.
DIMENSION_COST = {
    "technical_capability":    "medium",
    "research_output":         "high",
    "ip_filing":               "high",
    "infrastructure_or_facility": "high",
    "partnership_or_alliance": "medium",
    "funding_or_grant":        "high",
    "hiring_or_talent":        "medium",
    "regulatory_or_policy":    "medium",
    "market_positioning":      "low",
}

COST_MULTIPLIER = {"high": 1.0, "medium": 0.7, "low": 0.4}

DIMENSION_OBSERVABILITY = {
    "technical_capability":    "medium",
    "research_output":         "high",
    "ip_filing":               "high",
    "infrastructure_or_facility": "medium",
    "partnership_or_alliance": "high",
    "funding_or_grant":        "high",
    "hiring_or_talent":        "high",
    "regulatory_or_policy":    "high",
    "market_positioning":      "high",
}

COST_LABEL = {"high": "High-cost (hard to fake)", "medium": "Medium-cost", "low": "Low-cost (cheap talk)"}


def cost_class(dimension_key: str) -> str:
    return DIMENSION_COST.get(dimension_key, "medium")

def cost_multiplier(dimension_key: str) -> float:
    return COST_MULTIPLIER.get(cost_class(dimension_key), 0.7)

def cost_label(dimension_key: str) -> str:
    return COST_LABEL.get(cost_class(dimension_key), "Medium-cost")


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
    return DIMENSION_LABEL.get(key, key.replace("_", " ").title())

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
