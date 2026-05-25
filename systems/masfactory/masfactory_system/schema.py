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


SignalDimension = Literal[
    "technical_capability",
    "research_output",
    "partnership_or_alliance",
    "funding_or_grant",
    "ip_filing",
    "hiring_or_talent",
    "regulatory_or_policy",
    "market_positioning",
    "infrastructure_or_facility",
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
