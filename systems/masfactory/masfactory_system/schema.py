"""Pydantic models shared across nodes.

These describe the *data contracts* between agents in the graph. Both this
system and the Hermes-based System B write to the same Supabase tables, so
keeping the schema explicit here is the place to evolve it without breaking
the cross-system comparison.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


ActorCategory = Literal[
    "national_initiative",
    "university_or_research_hub",
    "ecosystem_builder",
    "private_company",
    "government",
]

SourceKind = Literal["arxiv", "website", "swissreg", "manual", "news"]


# Ehrenthal et al. (2026) four-signal scheme — the top-level taxonomy.
SignalType = Literal[
    "legitimacy",
    "customer_cocreation",
    "community_ecosystem",
    "future_trajectory",
]

# Sub-categories (dimensions) under the four signal_types. Eighteen total;
# sixteen match Ehrenthal's coded markers verbatim, two are explicit
# extensions documented in schema.yaml (funding_event, regulatory_recognition).
# Legacy v0.3.0 keys are migrated via the SQL block in persistence/schema.sql
# and `classification.legacy_dimension_map()`.
SignalDimension = Literal[
    # Legitimacy
    "leadership_expertise",
    "patents",
    "publications",
    "awards",
    "testimonials",
    "educational_outreach",
    "funding_event",
    "regulatory_recognition",
    # Customer co-creation
    "collaborations_applications",
    "pilots_pocs",
    "customer_training",
    # Community-ecosystem
    "cloud_platform_listings",
    "hpc_collaborations",
    "industry_partnerships",
    "academic_partnerships",
    # Future-trajectory
    "roadmaps",
    "milestones",
    "technological_advances",
    "long_horizon_claims",
]


class Actor(BaseModel):
    slug: str = Field(description="Lowercase machine identifier, e.g. 'eth-zurich-quantum-center'")
    name: str
    category: ActorCategory
    homepage: Optional[HttpUrl] = None
    arxiv_query: Optional[str] = Field(
        default=None,
        description="Optional arXiv search query — typically affiliation or author cluster.",
    )
    notes: Optional[str] = None


class Document(BaseModel):
    """Raw payload returned by a collector before the Extractor processes it."""

    source_kind: SourceKind
    source_url: str
    actor_slug: str
    title: Optional[str] = None
    text: str
    fetched_at: datetime
    content_hash: str


class SignalCandidate(BaseModel):
    """An Extractor's structured guess about something worth recording."""

    actor_slug: str
    source_kind: SourceKind
    source_url: str
    title: str
    summary: str
    evidence_quote: str = Field(description="Short verbatim snippet supporting the signal.")
    observed_at: Optional[datetime] = None


class ClassifiedSignal(SignalCandidate):
    """A SignalCandidate after the Classifier has labelled it."""

    dimension: SignalDimension
    # Top-level Ehrenthal four-signal scheme. Defaults to None for old code
    # paths that haven't been migrated yet — the Persistence node fills it
    # from `dimension` via classification.signal_type_for_dimension() if
    # the Classifier didn't emit it directly.
    signal_type: Optional[SignalType] = None
    is_technical: bool
    confidence: float = Field(ge=0.0, le=1.0)


class CritiqueDecision(BaseModel):
    """Critic's verdict per signal."""

    signal_index: int
    keep: bool
    reason: str
    duplicate_of: Optional[int] = None


class AnalystBrief(BaseModel):
    actor_slug: str
    summary_md: str
    notable_signal_indices: list[int]
