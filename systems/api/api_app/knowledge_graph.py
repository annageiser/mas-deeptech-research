"""Knowledge-graph builder — derives a typed entity / relationship graph
from public.signals + public.actors and returns it as plain JSON for the
frontend to render with any JS graph library.

v0.4.40 — refactored onto the kg_model abstractions (Entity / Relationship /
SemanticLink) without changing the historic wire shape. Two new families
of edges are gated behind opt-in query params:

  include_taxonomy   adds 4 SignalType nodes + DIMENSION_TO_SIGNAL_TYPE
                     edges (the Ehrenthal taxonomy hierarchy) plus
                     aggregated ACTOR_TO_SIGNAL_TYPE volume edges.

  include_semantic   adds ACTOR_TO_ACTOR_SEMANTIC edges computed via
                     centroid cosine similarity over the populated
                     signals.embedding column. No-op when embeddings
                     are off everywhere (the *_EMBEDDINGS=1 flags from
                     .env.example).

Both are off by default so any v0.4.39 client sees the exact same
response shape it always did.

Node types:
  - actor       (coloured by category, size ∝ distinct dimensions)
  - dimension   (the 19 v0.4.0 sub-categories)
  - signal_type (the 4 Ehrenthal categories — v0.4.40 additive)

Edge types:
  - actor-dim          actor → dimension (weight = signal count)
  - actor-actor        actor ↔ actor (weight = shared dimensions, ≥ threshold)
  - dim-signal-type    dimension → signal_type (taxonomy)        v0.4.40
  - actor-signal-type  actor → signal_type (aggregate volume)    v0.4.40
  - actor-actor-sim    actor ↔ actor (pgvector cosine similarity) v0.4.40
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from . import labels as L
from .kg_model import (
    EdgeType,
    Entity,
    Graph,
    NodeType,
    Relationship,
    SemanticLink,
    actor_id,
    dimension_id,
    signal_type_id,
)


SAMPLE_TITLES_PER_EDGE = 3

# Floor for ACTOR_TO_ACTOR_SEMANTIC edges. Centroid cosine in [-1, 1];
# 0.85 is a strong-similarity threshold that empirically keeps the
# edge count manageable (≤ ~3 edges per actor) when both systems are
# running with embeddings on.
DEFAULT_SEMANTIC_THRESHOLD = 0.85

# Cap on the number of semantic edges emitted so a fully-populated
# corpus doesn't drown the graph layout. Pairs are ranked by similarity
# descending; the top N survive.
MAX_SEMANTIC_EDGES = 60


def build_graph_json(
    signals_df: pd.DataFrame,
    actors_df: pd.DataFrame,
    *,
    shared_dim_threshold: int = 2,
    include_taxonomy: bool = False,
    include_semantic: bool = False,
    semantic_threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
) -> dict[str, Any]:
    """Build a JSON graph for the frontend.

    Backwards-compatible shape: nodes carry the same fields as before
    (`id`, `kind`, `label`, `color`, `size`, plus the domain-specific
    fields the GraphCanvas reads). Edges carry their own meaning so the
    inspector panel renders without a second API round-trip.
    """
    if signals_df.empty:
        return {"nodes": [], "edges": []}

    graph = Graph()

    # ---- 1. Existing edges (preserved verbatim from v0.4.0) ----
    actor_dim_counts, actor_dims, actor_dim_titles = _aggregate_actor_dimensions(signals_df)

    actor_meta = _actor_meta(actors_df)
    _add_actor_entities(graph, actor_dims, actor_meta)
    _add_dimension_entities(graph, actor_dims)
    _add_actor_to_dimension_edges(
        graph, actor_dim_counts, actor_meta, actor_dim_titles,
    )
    _add_actor_to_actor_shared_edges(
        graph, actor_dims, actor_meta, threshold=shared_dim_threshold,
    )

    # ---- 2. v0.4.40 additive: taxonomy hierarchy ----
    if include_taxonomy:
        _add_signal_type_entities(graph, actor_dims)
        _add_dimension_to_signal_type_edges(graph, actor_dims)
        _add_actor_to_signal_type_edges(
            graph, signals_df=signals_df, actor_meta=actor_meta,
        )

    # ---- 3. v0.4.40 additive: semantic similarity between actors ----
    if include_semantic:
        _add_actor_to_actor_semantic_edges(
            graph,
            signals_df=signals_df,
            actor_meta=actor_meta,
            threshold=semantic_threshold,
        )

    return graph.to_wire()


# ---------------------------------------------------------------------------
# Aggregation helpers (no I/O — pure DataFrame work)
# ---------------------------------------------------------------------------


def _aggregate_actor_dimensions(
    signals_df: pd.DataFrame,
) -> tuple[
    dict[tuple[str, str], int],
    dict[str, set[str]],
    dict[tuple[str, str], list[str]],
]:
    """Returns ((actor, dim) → count, actor → {dims}, (actor, dim) → sample_titles[])."""
    # Normalise legacy dimensions so the graph shows v0.4.0 keys even if
    # pre-migration rows are still in the result set.
    if "dimension" in signals_df.columns:
        signals_df = signals_df.copy()
        signals_df["dimension"] = signals_df["dimension"].apply(L.normalise_dimension)

    actor_dim_counts: dict[tuple[str, str], int] = {}
    actor_dims: dict[str, set[str]] = {}
    sort_col = "inserted_at" if "inserted_at" in signals_df.columns else None
    sorted_df = (signals_df.sort_values(sort_col, ascending=False)
                 if sort_col else signals_df)

    actor_dim_titles: dict[tuple[str, str], list[str]] = {}
    for _, s in sorted_df.iterrows():
        actor = s.get("actor_slug")
        dim = s.get("dimension")
        if not actor or not dim:
            continue
        actor_dim_counts[(actor, dim)] = actor_dim_counts.get((actor, dim), 0) + 1
        actor_dims.setdefault(actor, set()).add(dim)
        bucket = actor_dim_titles.setdefault((actor, dim), [])
        if len(bucket) < SAMPLE_TITLES_PER_EDGE:
            title = (s.get("title") or "").strip()
            if title and title not in bucket:
                bucket.append(title[:160])
    return actor_dim_counts, actor_dims, actor_dim_titles


def _actor_meta(actors_df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """slug → (display_name, category)."""
    if actors_df.empty:
        return {}
    return {
        row["slug"]: (row.get("name") or row["slug"], row.get("category") or "")
        for _, row in actors_df.iterrows()
    }


# ---------------------------------------------------------------------------
# Entity builders
# ---------------------------------------------------------------------------


def _add_actor_entities(
    graph: Graph,
    actor_dims: dict[str, set[str]],
    actor_meta: dict[str, tuple[str, str]],
) -> None:
    for actor, dims in actor_dims.items():
        name, cat = actor_meta.get(actor, (actor, ""))
        graph.add_entity(Entity(
            id=actor_id(actor),
            type=NodeType.ACTOR,
            label=name,
            color=L.CATEGORY_COLOR.get(cat, "#666"),
            size=10 + 4 * len(dims),
            properties={
                "actor_slug": actor,
                "category": cat,
                "category_label": L.category(cat) if cat else "",
                "dimensions": len(dims),
            },
        ))


def _add_dimension_entities(
    graph: Graph,
    actor_dims: dict[str, set[str]],
) -> None:
    all_dims = {d for dims in actor_dims.values() for d in dims}
    for dim in all_dims:
        st = L.signal_type_for(dim)
        graph.add_entity(Entity(
            id=dimension_id(dim),
            type=NodeType.DIMENSION,
            label=L.dimension(dim),
            color=L.SIGNAL_TYPE_COLOR.get(st, "#cbd5e1"),
            size=14,
            properties={
                "dimension_key": dim,
                "signal_type": st,
                "signal_type_label": L.signal_type_label(st),
                "cost_class": L.cost_class(dim),
            },
        ))


def _add_signal_type_entities(
    graph: Graph,
    actor_dims: dict[str, set[str]],
) -> None:
    """v0.4.40 — emit the four Ehrenthal categories as first-class nodes.

    Only emitted when at least one dimension in the current graph maps
    to that signal_type, so the canvas never grows empty top-level
    nodes for windows where (e.g.) no future_trajectory signals fired.
    """
    seen: set[str] = set()
    all_dims = {d for dims in actor_dims.values() for d in dims}
    for dim in all_dims:
        st = L.signal_type_for(dim)
        if not st or st in seen:
            continue
        seen.add(st)
        graph.add_entity(Entity(
            id=signal_type_id(st),
            type=NodeType.SIGNAL_TYPE,
            label=L.signal_type_label(st),
            color=L.SIGNAL_TYPE_COLOR.get(st, "#94a3b8"),
            size=22,
            properties={
                "signal_type_key": st,
                "short_label": L.SIGNAL_TYPE_SHORT.get(st, st),
            },
        ))


# ---------------------------------------------------------------------------
# Edge builders
# ---------------------------------------------------------------------------


def _add_actor_to_dimension_edges(
    graph: Graph,
    actor_dim_counts: dict[tuple[str, str], int],
    actor_meta: dict[str, tuple[str, str]],
    actor_dim_titles: dict[tuple[str, str], list[str]],
) -> None:
    for (actor, dim), count in actor_dim_counts.items():
        actor_name = actor_meta.get(actor, (actor, ""))[0]
        st = L.signal_type_for(dim)
        graph.add_relationship(Relationship(
            source=actor_id(actor),
            target=dimension_id(dim),
            type=EdgeType.ACTOR_TO_DIMENSION,
            weight=float(count),
            properties={
                "count": count,
                "actor_label": actor_name,
                "dimension_label": L.dimension(dim),
                "signal_type": st,
                "signal_type_label": L.signal_type_label(st),
                "cost_class": L.cost_class(dim),
                "sample_titles": actor_dim_titles.get((actor, dim), []),
            },
        ))


def _add_actor_to_actor_shared_edges(
    graph: Graph,
    actor_dims: dict[str, set[str]],
    actor_meta: dict[str, tuple[str, str]],
    *,
    threshold: int,
) -> None:
    actors_with_data = list(actor_dims.keys())
    for i, a in enumerate(actors_with_data):
        for b in actors_with_data[i + 1:]:
            shared = actor_dims[a] & actor_dims[b]
            if len(shared) < threshold:
                continue
            a_name = actor_meta.get(a, (a, ""))[0]
            b_name = actor_meta.get(b, (b, ""))[0]
            shared_signal_types = sorted({
                L.signal_type_label(L.signal_type_for(d)) for d in shared
            })
            graph.add_relationship(Relationship(
                source=actor_id(a),
                target=actor_id(b),
                type=EdgeType.ACTOR_TO_ACTOR_SHARED,
                weight=float(len(shared)),
                properties={
                    "actor_a_label": a_name,
                    "actor_b_label": b_name,
                    "shared": sorted(L.dimension(d) for d in shared),
                    "shared_signal_types": shared_signal_types,
                },
            ))


def _add_dimension_to_signal_type_edges(
    graph: Graph,
    actor_dims: dict[str, set[str]],
) -> None:
    """v0.4.40 — emit the 19-edge taxonomy (each dimension → its signal_type)."""
    all_dims = {d for dims in actor_dims.values() for d in dims}
    for dim in all_dims:
        st = L.signal_type_for(dim)
        if not st:
            continue
        graph.add_relationship(Relationship(
            source=dimension_id(dim),
            target=signal_type_id(st),
            type=EdgeType.DIMENSION_TO_SIGNAL_TYPE,
            weight=1.0,
            properties={
                "dimension_label": L.dimension(dim),
                "signal_type_label": L.signal_type_label(st),
            },
        ))


def _add_actor_to_signal_type_edges(
    graph: Graph,
    *,
    signals_df: pd.DataFrame,
    actor_meta: dict[str, tuple[str, str]],
) -> None:
    """v0.4.40 — emit per-actor aggregate volume per signal_type."""
    if signals_df.empty:
        return
    sdf = signals_df.copy()
    if "dimension" in sdf.columns:
        sdf["dimension"] = sdf["dimension"].apply(L.normalise_dimension)
    sdf["_st"] = sdf["dimension"].apply(L.signal_type_for)
    counts = sdf.groupby(["actor_slug", "_st"]).size().reset_index(name="count")
    for _, row in counts.iterrows():
        actor = row["actor_slug"]
        st = row["_st"]
        if not actor or not st:
            continue
        actor_name = actor_meta.get(actor, (actor, ""))[0]
        graph.add_relationship(Relationship(
            source=actor_id(actor),
            target=signal_type_id(st),
            type=EdgeType.ACTOR_TO_SIGNAL_TYPE,
            weight=float(row["count"]),
            properties={
                "count": int(row["count"]),
                "actor_label": actor_name,
                "signal_type_label": L.signal_type_label(st),
            },
        ))


def _add_actor_to_actor_semantic_edges(
    graph: Graph,
    *,
    signals_df: pd.DataFrame,
    actor_meta: dict[str, tuple[str, str]],
    threshold: float,
) -> None:
    """v0.4.40 — pairwise cosine similarity over per-actor centroid embeddings.

    Centroid = mean of an actor's signal embeddings in the window. Two
    actors with centroid cosine ≥ `threshold` get a SemanticLink. Pairs
    are sorted by similarity desc and capped at MAX_SEMANTIC_EDGES so
    the canvas layout stays readable.

    Silently no-op when fewer than 2 actors have a non-null embedding in
    the window (`MASF_EMBEDDINGS` / `HRM_EMBEDDINGS` are off in
    `.env.example` by default — operators turn them on per `docs/iterations/v0.4.20-…`).
    """
    if "embedding" not in signals_df.columns or signals_df.empty:
        return

    # Filter to rows that actually carry an embedding vector.
    df = signals_df.dropna(subset=["embedding"]).copy()
    if df.empty:
        return

    centroids = _compute_actor_centroids(df)
    if len(centroids) < 2:
        return

    pairs: list[tuple[str, str, float]] = []
    actors = list(centroids.keys())
    for i, a in enumerate(actors):
        for b in actors[i + 1:]:
            sim = _cosine(centroids[a], centroids[b])
            if sim is None or sim < threshold:
                continue
            pairs.append((a, b, sim))
    if not pairs:
        return

    pairs.sort(key=lambda p: -p[2])
    for a, b, sim in pairs[:MAX_SEMANTIC_EDGES]:
        a_name = actor_meta.get(a, (a, ""))[0]
        b_name = actor_meta.get(b, (b, ""))[0]
        graph.add_relationship(SemanticLink(
            source=actor_id(a),
            target=actor_id(b),
            type=EdgeType.ACTOR_TO_ACTOR_SEMANTIC,
            properties={
                "actor_a_label": a_name,
                "actor_b_label": b_name,
            },
            similarity=sim,
        ))


def _compute_actor_centroids(df_with_embeddings: pd.DataFrame) -> dict[str, list[float]]:
    """Mean embedding per actor. Empty list when an actor has no vectors."""
    centroids: dict[str, list[float]] = {}
    for actor, sub in df_with_embeddings.groupby("actor_slug"):
        vectors: list[list[float]] = []
        for emb in sub["embedding"]:
            vec = _coerce_vector(emb)
            if vec is not None:
                vectors.append(vec)
        if not vectors:
            continue
        # Element-wise mean — assume all vectors have the same dimension
        # (768d BGE-base-en-v1.5). Defensive: take the min length.
        n = min(len(v) for v in vectors)
        centroid = [sum(v[i] for v in vectors) / len(vectors) for i in range(n)]
        centroids[actor] = centroid
    return centroids


def _coerce_vector(value: Any) -> list[float] | None:
    """Supabase REST returns vector(768) as a JSON list of floats. PostgREST
    sometimes wraps it as a string ('[0.1,0.2,...]') — handle both."""
    if value is None:
        return None
    if isinstance(value, list):
        try:
            return [float(x) for x in value]
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                return [float(x) for x in s[1:-1].split(",") if x.strip()]
            except ValueError:
                return None
    return None


def _cosine(a: list[float], b: list[float]) -> float | None:
    if not a or not b:
        return None
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    norm_a = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    norm_b = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if norm_a == 0.0 or norm_b == 0.0:
        return None
    return dot / (norm_a * norm_b)
