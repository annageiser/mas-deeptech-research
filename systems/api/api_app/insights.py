"""Descriptive insight templates over the signal store (persona-lens layer).

Each insight is a *pattern + source-attributed evidence + neutral framing*
derived from signals already collected. No new data, no external sources, no
prescriptive scoring — this stays inside the thesis's descriptive scope. The
associations are correlational and confined to the retrieval window; they are
not causal claims.

Consumed by GET /api/insights and the web /personas/[id] pages. The pure
`compute_insights()` takes DataFrames so it is unit-testable without Supabase;
`insights_payload()` is the thin fetch-and-wrap used by the route.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd

from . import data_access as da
from . import labels as L
from .scoring import actor_impact_table, attach_actor_metadata

# Which insight types each persona cares about, in priority order. Also the
# canonical persona id list. Personas map to the five stakeholder lenses
# documented in thesis §3.2 (Competitor folded into consultant + corporate).
PERSONA_INSIGHT_TYPES: dict[str, list[str]] = {
    "investor":   ["rising", "funding", "narrative_heavy", "concentration"],
    "researcher": ["new_ground", "broad_front", "rising", "coverage_gap"],
    "consultant": ["concentration", "broad_front", "narrative_heavy", "rising", "coverage_gap"],
    "corporate":  ["narrative_heavy", "broad_front", "rising", "coverage_gap"],
    "government": ["funding", "regulatory", "coverage_gap", "concentration"],
}
PERSONAS = list(PERSONA_INSIGHT_TYPES.keys())


def _s(v: Any) -> str:
    """NaN/None-safe string coercion."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v)


def compute_insights(
    sig: pd.DataFrame,
    scores: pd.DataFrame,
    actors_df: pd.DataFrame,
    *,
    persona: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Derive the descriptive insight list. Pure — no I/O."""
    if sig is None or sig.empty:
        return []

    now = now or datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    sig = sig.copy()
    sig["dimension"] = sig["dimension"].map(L.normalise_dimension)
    sig["dim_label"] = sig["dimension"].map(L.dimension)
    sig["st"] = sig["dimension"].map(L.signal_type_for)
    sig["st_label"] = sig["st"].map(L.signal_type_label)
    sig["inserted_dt"] = pd.to_datetime(sig["inserted_at"], utc=True, errors="coerce")
    sig = sig.sort_values("inserted_dt", ascending=False)

    name_map: dict[str, str] = {}
    if scores is not None and not scores.empty and "name" in scores.columns:
        name_map = {str(a): str(n) for a, n in zip(scores["actor_slug"], scores["name"])}

    def nm(slug: str) -> str:
        return name_map.get(str(slug), str(slug))

    def evidence_for(actor_slug: str, dims: Optional[set[str]] = None, n: int = 3) -> list[dict]:
        d = sig[sig["actor_slug"] == actor_slug]
        if dims is not None:
            d = d[d["dimension"].isin(dims)]
        out = []
        for _, r in d.head(n).iterrows():
            out.append({
                "actor_name": nm(actor_slug),
                "title": (_s(r["title"]) or _s(r["summary"]))[:140],
                "source_url": _s(r["source_url"]) or None,
                "dimension_label": _s(r["dim_label"]),
                "signal_type_label": _s(r["st_label"]),
            })
        return out

    items: list[dict[str, Any]] = []

    def add(typ, personas, title, detail, *, id_suffix=None,
            actor_slug=None, actor_name=None, metrics=None, evidence=None, severity="info"):
        items.append({
            "id": f"{typ}:{id_suffix or actor_slug or 'eco'}",
            "type": typ,
            "personas": personas,
            "severity": severity,
            "title": title,
            "detail": detail,
            "actor_slug": actor_slug,
            "actor_name": actor_name,
            "metrics": metrics or {},
            "evidence": evidence or [],
        })

    has_scores = scores is not None and not scores.empty

    # --- rising: positive week-over-week trend on a substantiated actor ---
    if has_scores:
        rising = scores[(scores["momentum"] > 0) & (scores["credibility"] > 0)]
        for _, r in rising.sort_values("credibility", ascending=False).head(3).iterrows():
            add("rising", ["investor", "corporate", "consultant"],
                f"{r['name']} is accelerating",
                f"+{int(r['momentum'])} signals week-over-week, with a Cost-Weighted Signal "
                f"Score of {float(r['credibility']):.2f} and a {int(round(float(r['cheap_talk_ratio']) * 100))}% "
                f"Low-Cost Signal Share.",
                actor_slug=str(r["actor_slug"]), actor_name=str(r["name"]),
                metrics={"momentum": int(r["momentum"]), "credibility": float(r["credibility"]),
                         "cheap_talk_ratio": float(r["cheap_talk_ratio"])},
                evidence=evidence_for(str(r["actor_slug"]), n=3), severity="watch")

    # --- narrative_heavy: positioning outweighing costly evidence ---
    if has_scores:
        nh = scores[(scores["signal_count"] >= 3) & (scores["cheap_talk_ratio"] >= 0.5)
                    & (scores["diversity"] <= 2)]
        for _, r in nh.sort_values("cheap_talk_ratio", ascending=False).head(3).iterrows():
            add("narrative_heavy", ["investor", "consultant", "corporate"],
                f"{r['name']}'s signalling is positioning-led",
                f"{int(round(float(r['cheap_talk_ratio']) * 100))}% of {r['name']}'s signals are low-cost, "
                f"across only {int(r['diversity'])} dimension(s) — positioning is outweighing costly "
                f"evidence in this window.",
                actor_slug=str(r["actor_slug"]), actor_name=str(r["name"]),
                metrics={"cheap_talk_ratio": float(r["cheap_talk_ratio"]), "diversity": int(r["diversity"]),
                         "signal_count": int(r["signal_count"])},
                evidence=evidence_for(str(r["actor_slug"]), n=3))

    # --- broad_front: signalling across many dimensions ---
    if has_scores:
        bf = scores[scores["diversity"] >= 5]
        for _, r in bf.sort_values("diversity", ascending=False).head(3).iterrows():
            add("broad_front", ["consultant", "researcher", "corporate"],
                f"{r['name']} is signalling on {int(r['diversity'])} dimensions",
                f"{r['name']} is active across {int(r['diversity'])} distinct signal dimensions "
                f"(broad, multi-front signalling) rather than a single-note story.",
                actor_slug=str(r["actor_slug"]), actor_name=str(r["name"]),
                metrics={"diversity": int(r["diversity"]), "signal_count": int(r["signal_count"])},
                evidence=evidence_for(str(r["actor_slug"]), n=3))

    # --- new_ground: (actor, dimension) first-appears in the last 7 days ---
    prior = sig[sig["inserted_dt"] < week_ago]
    if not prior.empty:  # only meaningful when there's a prior baseline in-window
        recent = sig[sig["inserted_dt"] >= week_ago]
        prior_pairs = set(zip(prior["actor_slug"], prior["dimension"]))
        seen: set = set()
        for _, r in recent.iterrows():
            key = (r["actor_slug"], r["dimension"])
            if key in prior_pairs or key in seen:
                continue
            seen.add(key)
            add("new_ground", ["researcher", "consultant"],
                f"{nm(r['actor_slug'])} opened new ground: {_s(r['dim_label'])}",
                f"The first {_s(r['dim_label'])} signal for {nm(r['actor_slug'])} in this window "
                f"appeared in the last 7 days.",
                id_suffix=f"{r['actor_slug']}:{r['dimension']}",
                actor_slug=str(r["actor_slug"]), actor_name=nm(r["actor_slug"]),
                metrics={"dimension": _s(r["dimension"]), "signal_type": _s(r["st"])},
                evidence=[{
                    "actor_name": nm(r["actor_slug"]),
                    "title": (_s(r["title"]) or _s(r["summary"]))[:140],
                    "source_url": _s(r["source_url"]) or None,
                    "dimension_label": _s(r["dim_label"]),
                    "signal_type_label": _s(r["st_label"]),
                }], severity="watch")
            if len(seen) >= 5:
                break

    # --- funding: recent funding-related activity ---
    fund = sig[sig["dimension"] == "funding_event"]
    if not fund.empty:
        f_actors = list(dict.fromkeys(str(a) for a in fund["actor_slug"]))
        names = [nm(a) for a in f_actors][:6]
        add("funding", ["investor", "government"],
            "Recent funding-related signals",
            f"{len(fund)} funding-event signal(s) from {len(f_actors)} actor(s): "
            f"{', '.join(names)}{' …' if len(f_actors) > 6 else ''}.",
            id_suffix="all",
            metrics={"count": int(len(fund)), "actors": int(len(f_actors))},
            evidence=[{
                "actor_name": nm(r["actor_slug"]),
                "title": (_s(r["title"]) or _s(r["summary"]))[:140],
                "source_url": _s(r["source_url"]) or None,
                "dimension_label": _s(r["dim_label"]),
                "signal_type_label": _s(r["st_label"]),
            } for _, r in fund.head(3).iterrows()])

    # --- regulatory: recognition / policy signals ---
    reg = sig[sig["dimension"] == "regulatory_recognition"]
    if not reg.empty:
        r_actors = list(dict.fromkeys(str(a) for a in reg["actor_slug"]))
        add("regulatory", ["government"],
            "Regulatory-recognition activity",
            f"{len(reg)} regulatory-recognition signal(s) from {len(r_actors)} actor(s): "
            f"{', '.join(nm(a) for a in r_actors[:6])}.",
            id_suffix="all",
            metrics={"count": int(len(reg)), "actors": int(len(r_actors))},
            evidence=[{
                "actor_name": nm(r["actor_slug"]),
                "title": (_s(r["title"]) or _s(r["summary"]))[:140],
                "source_url": _s(r["source_url"]) or None,
                "dimension_label": _s(r["dim_label"]),
                "signal_type_label": _s(r["st_label"]),
            } for _, r in reg.head(3).iterrows()])

    # --- coverage_gap: dimensions / actors with no activity this window ---
    scheme_dims = {d for d in L.DIMENSION_WEIGHT.keys() if L.signal_type_for(d)}
    present = set(sig["dimension"].unique())
    missing = sorted(scheme_dims - present)
    if missing:
        labels = [L.dimension(d) for d in missing][:8]
        add("coverage_gap", ["government", "consultant", "researcher"],
            f"{len(missing)} signal dimension(s) have no activity this window",
            "Dimensions with zero signals in the current window: "
            f"{', '.join(labels)}{' …' if len(missing) > 8 else ''}.",
            id_suffix="dimensions",
            metrics={"missing_count": int(len(missing))})
    if actors_df is not None and not actors_df.empty:
        total_actors = int(len(actors_df))
        active = int(scores["actor_slug"].nunique()) if has_scores else 0
        silent = total_actors - active
        if silent > 0:
            add("coverage_gap", ["government", "consultant"],
                f"{silent} of {total_actors} tracked actors are silent this window",
                f"{silent} of the {total_actors} tracked Swiss quantum actors produced no signals "
                f"in the current window — the manual-spot-check targets. Public sources only; "
                f"absence of a signal is not absence of activity.",
                id_suffix="actors",
                metrics={"silent": silent, "total": total_actors, "active": active})

    # --- concentration: how top-heavy the activity is ---
    if has_scores and float(scores["impact"].sum()) > 0:
        srt = scores.sort_values("impact", ascending=False)
        top3 = srt.head(3)
        pct = 100.0 * float(top3["impact"].sum()) / float(scores["impact"].sum())
        add("concentration", ["government", "consultant", "investor"],
            "Signal activity is concentrated at the top",
            f"The top {len(top3)} actors ({', '.join(str(n) for n in top3['name'])}) account for "
            f"{pct:.0f}% of weighted signal activity across {len(scores)} active actors.",
            id_suffix="all",
            metrics={"top_share_pct": round(pct, 1), "active_actors": int(len(scores))})

    # --- persona filter + ordering ---
    if persona and persona in PERSONA_INSIGHT_TYPES:
        order = {t: i for i, t in enumerate(PERSONA_INSIGHT_TYPES[persona])}
        items = [i for i in items if persona in i["personas"]]
        items.sort(key=lambda i: order.get(i["type"], 99))

    return items


def insights_payload(system: Optional[str], days: int, persona: Optional[str] = None) -> dict:
    """Fetch + compute. Thin wrapper used by the /api/insights route."""
    sig = da.signals(system=system, days=days)
    scores = attach_actor_metadata(actor_impact_table(sig), da.actors())
    if not scores.empty:
        scores["name"] = scores.apply(lambda r: r.get("name") or r["actor_slug"], axis=1)
        scores["category_label"] = scores["category"].map(lambda c: L.category(c) if c else "—")
    items = compute_insights(sig, scores, da.actors(), persona=persona)
    return {
        "insights": items,
        "count": len(items),
        "persona": persona if persona in PERSONA_INSIGHT_TYPES else None,
        "days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
