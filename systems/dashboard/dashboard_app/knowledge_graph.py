"""Knowledge graph rendering — actors + signal dimensions + co-occurrence edges.

Builds a networkx graph from the signals table:
- Node type 1: actor (slug + category)
- Node type 2: dimension
- Edge: actor → dimension if any signal exists with that pair (weight = count)
- Edge: actor ↔ actor if they share ≥ N dimensions (weight = shared count)

Renders to a self-contained HTML string via pyvis so Streamlit can embed.
"""

from __future__ import annotations

import math
import tempfile
from typing import Optional

import networkx as nx
import pandas as pd
from pyvis.network import Network


CATEGORY_COLOR = {
    "national_initiative": "#1f77b4",
    "university_or_research_hub": "#2ca02c",
    "ecosystem_builder": "#9467bd",
    "private_company": "#ff7f0e",
    "government": "#8c564b",
}


def build_graph(signals_df: pd.DataFrame, actors_df: pd.DataFrame, *, shared_dim_threshold: int = 2) -> nx.Graph:
    g = nx.Graph()
    if signals_df.empty:
        return g

    actor_meta = {
        row["slug"]: (row.get("name") or row["slug"], row.get("category") or "")
        for _, row in actors_df.iterrows()
    } if not actors_df.empty else {}

    # Actor + dimension nodes
    actor_dim_counts: dict[tuple[str, str], int] = {}
    actor_dims: dict[str, set[str]] = {}
    for _, s in signals_df.iterrows():
        actor = s.get("actor_slug")
        dim = s.get("dimension")
        if not actor or not dim:
            continue
        actor_dim_counts[(actor, dim)] = actor_dim_counts.get((actor, dim), 0) + 1
        actor_dims.setdefault(actor, set()).add(dim)

    for actor, dims in actor_dims.items():
        name, category = actor_meta.get(actor, (actor, ""))
        g.add_node(
            f"a:{actor}",
            kind="actor",
            label=name,
            title=f"{name}\n{category}\n{len(dims)} dimensions",
            color=CATEGORY_COLOR.get(category, "#666"),
            size=10 + 4 * len(dims),
        )
    for dim in {d for dims in actor_dims.values() for d in dims}:
        g.add_node(f"d:{dim}", kind="dimension", label=dim, color="#cccccc", size=14)

    # Actor → dimension edges
    for (actor, dim), count in actor_dim_counts.items():
        g.add_edge(f"a:{actor}", f"d:{dim}", weight=count, kind="actor-dim", title=f"{count} signal(s)")

    # Actor ↔ actor edges (shared dimensions)
    actors_with_data = list(actor_dims.keys())
    for i, a in enumerate(actors_with_data):
        for b in actors_with_data[i + 1 :]:
            shared = actor_dims[a] & actor_dims[b]
            if len(shared) >= shared_dim_threshold:
                g.add_edge(
                    f"a:{a}",
                    f"a:{b}",
                    weight=len(shared),
                    kind="actor-actor",
                    title=f"shared dims: {', '.join(sorted(shared))}",
                )
    return g


def render_html(g: nx.Graph, *, height: str = "650px") -> str:
    net = Network(height=height, width="100%", bgcolor="#ffffff", font_color="#222")
    net.from_nx(g)
    net.repulsion(node_distance=180, central_gravity=0.2, spring_length=110, spring_strength=0.08)
    # Pyvis writes to file; read back as string.
    with tempfile.NamedTemporaryFile(suffix=".html", mode="w+", delete=False) as fh:
        net.save_graph(fh.name)
        fh.seek(0)
        return fh.read()
