"""Knowledge-graph builder — returns plain JSON (nodes + edges) for the
frontend to render with any JS graph library.

Node types:
  - actor      (coloured by category, size ∝ distinct dimensions)
  - dimension  (signal type)
Edges:
  - actor → dimension  (weight = signal count for that pair)
  - actor ↔ actor      (weight = shared dimensions, ≥ threshold)
"""

from __future__ import annotations

import pandas as pd

from . import labels as L


SAMPLE_TITLES_PER_EDGE = 3


def build_graph_json(signals_df: pd.DataFrame, actors_df: pd.DataFrame, *, shared_dim_threshold: int = 2) -> dict:
    """Build a JSON graph for the frontend.

    Edges carry their own meaning so the frontend can render a tooltip
    / inspector panel without a second API round-trip:
      - actor-dim edges include `count` + `sample_titles` (up to 3 most-
        recent signal titles for that (actor, dimension) pair) +
        `dimension_label` + `signal_type_label` + `cost_class`.
      - actor-actor edges include `shared` (list of dimension labels) +
        `signal_types` (the set of Ehrenthal categories the actors share).
    """
    if signals_df.empty:
        return {"nodes": [], "edges": []}

    actor_meta = {
        row["slug"]: (row.get("name") or row["slug"], row.get("category") or "")
        for _, row in actors_df.iterrows()
    } if not actors_df.empty else {}

    # Normalise legacy dimensions so the graph shows v0.4.0 keys even if
    # pre-migration rows are still in the result set.
    if "dimension" in signals_df.columns:
        signals_df = signals_df.copy()
        signals_df["dimension"] = signals_df["dimension"].apply(L.normalise_dimension)

    actor_dim_counts: dict[tuple[str, str], int] = {}
    actor_dims: dict[str, set[str]] = {}
    # For per-edge sample-titles: keep top-N most recent (by inserted_at if
    # present) per (actor, dim) pair. Falls back to insertion order otherwise.
    sort_col = "inserted_at" if "inserted_at" in signals_df.columns else None
    if sort_col:
        signals_sorted = signals_df.sort_values(sort_col, ascending=False)
    else:
        signals_sorted = signals_df

    actor_dim_titles: dict[tuple[str, str], list[str]] = {}

    for _, s in signals_sorted.iterrows():
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

    nodes: list[dict] = []
    for actor, dims in actor_dims.items():
        name, cat = actor_meta.get(actor, (actor, ""))
        nodes.append({
            "id": f"a:{actor}",
            "kind": "actor",
            "label": name,
            "actor_slug": actor,
            "category": cat,
            "category_label": L.category(cat) if cat else "",
            "color": L.CATEGORY_COLOR.get(cat, "#666"),
            "size": 10 + 4 * len(dims),
            "dimensions": len(dims),
        })
    for dim in {d for dims in actor_dims.values() for d in dims}:
        nodes.append({
            "id": f"d:{dim}",
            "kind": "dimension",
            "label": L.dimension(dim),
            "dimension_key": dim,
            "signal_type": L.signal_type_for(dim),
            "signal_type_label": L.signal_type_label(L.signal_type_for(dim)),
            "cost_class": L.cost_class(dim),
            "color": L.SIGNAL_TYPE_COLOR.get(L.signal_type_for(dim), "#cbd5e1"),
            "size": 14,
        })

    edges: list[dict] = []
    for (actor, dim), count in actor_dim_counts.items():
        actor_name = actor_meta.get(actor, (actor, ""))[0]
        edges.append({
            "source": f"a:{actor}", "target": f"d:{dim}",
            "weight": count,
            "kind": "actor-dim",
            "count": count,
            "actor_label": actor_name,
            "dimension_label": L.dimension(dim),
            "signal_type": L.signal_type_for(dim),
            "signal_type_label": L.signal_type_label(L.signal_type_for(dim)),
            "cost_class": L.cost_class(dim),
            "sample_titles": actor_dim_titles.get((actor, dim), []),
        })

    actors_with_data = list(actor_dims.keys())
    for i, a in enumerate(actors_with_data):
        for b in actors_with_data[i + 1:]:
            shared = actor_dims[a] & actor_dims[b]
            if len(shared) >= shared_dim_threshold:
                a_name = actor_meta.get(a, (a, ""))[0]
                b_name = actor_meta.get(b, (b, ""))[0]
                shared_signal_types = sorted({
                    L.signal_type_label(L.signal_type_for(d)) for d in shared
                })
                edges.append({
                    "source": f"a:{a}", "target": f"a:{b}",
                    "weight": len(shared), "kind": "actor-actor",
                    "actor_a_label": a_name,
                    "actor_b_label": b_name,
                    "shared": sorted(L.dimension(d) for d in shared),
                    "shared_signal_types": shared_signal_types,
                })

    return {"nodes": nodes, "edges": edges}
