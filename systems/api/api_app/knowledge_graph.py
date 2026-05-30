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


def build_graph_json(signals_df: pd.DataFrame, actors_df: pd.DataFrame, *, shared_dim_threshold: int = 2) -> dict:
    if signals_df.empty:
        return {"nodes": [], "edges": []}

    actor_meta = {
        row["slug"]: (row.get("name") or row["slug"], row.get("category") or "")
        for _, row in actors_df.iterrows()
    } if not actors_df.empty else {}

    actor_dim_counts: dict[tuple[str, str], int] = {}
    actor_dims: dict[str, set[str]] = {}
    for _, s in signals_df.iterrows():
        actor = s.get("actor_slug")
        dim = s.get("dimension")
        if not actor or not dim:
            continue
        actor_dim_counts[(actor, dim)] = actor_dim_counts.get((actor, dim), 0) + 1
        actor_dims.setdefault(actor, set()).add(dim)

    nodes: list[dict] = []
    for actor, dims in actor_dims.items():
        name, cat = actor_meta.get(actor, (actor, ""))
        nodes.append({
            "id": f"a:{actor}",
            "kind": "actor",
            "label": name,
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
            "color": "#cbd5e1",
            "size": 14,
        })

    edges: list[dict] = []
    for (actor, dim), count in actor_dim_counts.items():
        edges.append({
            "source": f"a:{actor}", "target": f"d:{dim}",
            "weight": count, "kind": "actor-dim",
        })

    actors_with_data = list(actor_dims.keys())
    for i, a in enumerate(actors_with_data):
        for b in actors_with_data[i + 1:]:
            shared = actor_dims[a] & actor_dims[b]
            if len(shared) >= shared_dim_threshold:
                edges.append({
                    "source": f"a:{a}", "target": f"a:{b}",
                    "weight": len(shared), "kind": "actor-actor",
                    "shared": sorted(L.dimension(d) for d in shared),
                })

    return {"nodes": nodes, "edges": edges}
