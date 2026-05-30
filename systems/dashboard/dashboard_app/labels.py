"""Human-readable labels for everything the dashboard exposes.

Every place the dashboard would otherwise show a DB column name or an
internal slug, look here first. Stakeholders (researchers, investors,
business advisors) shouldn't have to learn `actor_slug` or `is_technical`.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Signal-classification dimensions (taxonomy in
# systems/masfactory/.../classification/schema.yaml)
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

# Short hint shown on hover
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

# Which dimensions count as "evidence of capability" vs "evidence of legitimacy".
# Grounded in the disposition's signaling-theory framing (Suchman 1995,
# Knight & Cavusgil 2004, Ehrenthal et al. 2026).
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

# Weight per dimension when computing an Impact score.
#
# CANONICAL SOURCE: systems/masfactory/masfactory_system/classification/schema.yaml
# Keep these values in sync with the `weight` field there. The dashboard reads
# them from this file (not the YAML) because the dashboard container doesn't
# bundle the masfactory package. If you edit one place, edit the other.
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

# Signal-cost class per dimension — the heart of signalling theory: costly,
# hard-to-fake signals (Rieger et al. 2025; Suchman 1995) carry more
# information than cheap talk. Mirrors `signal_cost` in schema.yaml.
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

# Credibility multiplier per cost class. Mirrors `cost_classes` in schema.yaml.
COST_MULTIPLIER = {"high": 1.0, "medium": 0.7, "low": 0.4}

# Public observability per dimension. Mirrors `observability` in schema.yaml.
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
# Actor categories (from data/raw/actors.yaml)
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


# ---------------------------------------------------------------------------
# Systems (the two MAS being compared)
# ---------------------------------------------------------------------------

SYSTEM_LABEL = {
    "masfactory": "System A · MASFactory",
    "hermes":     "System B · Hermes",
}

SYSTEM_SHORT = {
    "masfactory": "System A",
    "hermes":     "System B",
}


# ---------------------------------------------------------------------------
# Source kinds (where a signal came from)
# ---------------------------------------------------------------------------

SOURCE_KIND_LABEL = {
    "arxiv":    "arXiv paper",
    "website":  "Actor website",
    "news":     "News article",
    "swissreg": "Swissreg patent",
    "manual":   "Manual entry",
}


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

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
