"""Knowledge-graph data model — typed entities, relationships, semantic links.

v0.4.40 introduces this small abstraction layer so the in-process graph
builder (`knowledge_graph.py`) and the wire format both speak the same
vocabulary. The model is deliberately analogous to the codebase-memory-mcp
conceptual pattern (typed Entity + typed Relationship + optional
semantic-similarity edges) but lives in a *different domain* — the
research-data graph (actors, signal types, dimensions, signals), not the
source-code graph.

We do NOT persist these into Supabase as their own tables. The graph is
derived per request from public.signals + public.actors so it never
drifts from the live corpus. The dataclasses below are the in-memory
representation used by the builder; `to_node()` / `to_edge()` render
them into the wire shape the website's GraphCanvas already consumes.

Backwards compatibility: the wire shape stays compatible with the
pre-v0.4.40 GraphCanvas. New `EdgeType` and `NodeType` values are
additive — only emitted when the caller opts in via
`include_taxonomy=true` / `include_semantic=true`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    """Kinds of entities visible in the research graph."""

    # Pre-v0.4.40 — present in every response.
    ACTOR = "actor"
    DIMENSION = "dimension"

    # v0.4.40 additive — present only when `include_taxonomy=true`.
    SIGNAL_TYPE = "signal_type"


class EdgeType(str, Enum):
    """Kinds of relationships between research entities.

    String values are the wire-format kinds the existing GraphCanvas
    already understands. New values added here are additive; the
    frontend treats unknown kinds as fall-through `actor-dim` shapes
    (see `lib/types.ts:KnowledgeGraphEdge.kind`).
    """

    # Pre-v0.4.40 — always emitted.
    ACTOR_TO_DIMENSION = "actor-dim"
    ACTOR_TO_ACTOR_SHARED = "actor-actor"

    # v0.4.40 additive — only emitted when their feature gate is on.
    DIMENSION_TO_SIGNAL_TYPE = "dim-signal-type"      # taxonomy edge
    ACTOR_TO_SIGNAL_TYPE = "actor-signal-type"        # aggregate volume
    ACTOR_TO_ACTOR_SEMANTIC = "actor-actor-sim"       # pgvector cosine similarity


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    """A typed node in the research knowledge graph.

    `properties` is the bag of domain-specific fields the renderer
    surfaces (category for actors, signal_type for dimensions, etc.).
    The serialiser spreads it into the top-level dict so the wire shape
    matches the pre-v0.4.40 layout.
    """

    id: str
    type: NodeType
    label: str
    color: str = "#888"
    size: int = 12
    properties: dict[str, Any] = field(default_factory=dict)

    def to_node(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.type.value,
            "label": self.label,
            "color": self.color,
            "size": self.size,
        }
        # Spread domain-specific properties at the top level — preserves
        # the historic wire shape that the GraphCanvas reads
        # (actor_slug, category, signal_type, cost_class, …).
        for k, v in self.properties.items():
            if k not in out:
                out[k] = v
        return out


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


@dataclass
class Relationship:
    """A typed edge between two Entity ids."""

    source: str
    target: str
    type: EdgeType
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)

    def to_edge(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "kind": self.type.value,
            "weight": self.weight,
        }
        for k, v in self.properties.items():
            if k not in out:
                out[k] = v
        return out


@dataclass
class SemanticLink(Relationship):
    """A pgvector-cosine-similarity edge between two entities.

    Distinct subclass so the renderer can show it differently (dashed
    stroke, similarity-tinted colour) without an extra wire-format
    branch. The `similarity` field is also surfaced in `properties`
    so the wire payload stays a flat dict.
    """

    similarity: float = 0.0

    def __post_init__(self) -> None:
        # Mirror similarity into properties for the wire shape.
        self.properties.setdefault("similarity", round(self.similarity, 4))
        # Weight is the similarity by default — heavier line = closer match.
        if self.weight == 1.0:
            self.weight = round(self.similarity, 4)


# ---------------------------------------------------------------------------
# Graph container
# ---------------------------------------------------------------------------


@dataclass
class Graph:
    """An in-memory graph: entities + relationships keyed by id.

    Iteration order is insertion order so the renderer's layout is
    stable across requests (no surprise re-orderings between cache hits
    and cache misses).
    """

    entities: dict[str, Entity] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)

    def add_entity(self, e: Entity) -> Entity:
        existing = self.entities.get(e.id)
        if existing is not None:
            return existing
        self.entities[e.id] = e
        return e

    def add_relationship(self, r: Relationship) -> None:
        self.relationships.append(r)

    def to_wire(self) -> dict[str, Any]:
        return {
            "nodes": [e.to_node() for e in self.entities.values()],
            "edges": [r.to_edge() for r in self.relationships],
        }


# ---------------------------------------------------------------------------
# Id helpers
# ---------------------------------------------------------------------------


def actor_id(slug: str) -> str:
    return f"a:{slug}"


def dimension_id(key: str) -> str:
    return f"d:{key}"


def signal_type_id(key: str) -> str:
    return f"s:{key}"


def parse_id(node_id: str) -> tuple[NodeType | None, str]:
    """Reverse the prefix scheme — returns (NodeType or None, raw_key)."""
    if not node_id or ":" not in node_id:
        return None, node_id
    prefix, raw = node_id.split(":", 1)
    return {"a": NodeType.ACTOR, "d": NodeType.DIMENSION, "s": NodeType.SIGNAL_TYPE}.get(prefix), raw
