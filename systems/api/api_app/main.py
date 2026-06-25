"""FastAPI app — read-only JSON over the shared Supabase signal database.

All scoring is the literature-grounded model in scoring.py (impact,
credibility = cost-discounted impact, cheap_talk_ratio, authority, momentum,
diversity). See /api/meta for the full methodology.
"""

from __future__ import annotations

import math
from typing import Any, Literal, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import data_access as da
from . import labels as L
from . import reports as R
from . import training as T
from .config import load_settings
from .coverage import coverage_payload
from .knowledge_graph import build_graph_json
from .meta import meta_payload
from .scoring import actor_impact_table, attach_actor_metadata, ecosystem_summary


app = FastAPI(
    title="MAS Deep-Tech Research API",
    version="0.1.0",
    description="Read-only JSON over the Swiss-quantum-ecosystem signal database. "
                "Literature-grounded signalling-theory scoring.",
)

_settings = load_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# v0.4.37: 'manual' added as a first-class producer alongside the two MAS.
# Manual signals are propagated into public.signals by sync_manual_signals.py
# (called nightly + after each manual-signals POST/PATCH) and appear in
# /api/signals + /api/compare as their own slice. Pre-reg metrics (H1, H2,
# H3, H4, H5) still compute on masfactory + hermes only — see
# systems/evaluation/eval_app/runner.py for the explicit filter.
VALID_SYSTEMS = {"masfactory", "hermes", "manual"}


# ---------- helpers ----------

def _norm_system(system: Optional[str]) -> Optional[str]:
    if system in (None, "", "both", "all"):
        return None
    if system not in VALID_SYSTEMS:
        raise HTTPException(status_code=400, detail=f"unknown system '{system}'")
    return system


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame → JSON-safe list of dicts (NaN/inf → None)."""
    if df is None or df.empty:
        return []
    safe = df.where(pd.notnull(df), None)
    out: list[dict[str, Any]] = []
    for row in safe.to_dict(orient="records"):
        clean = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean[k] = None
            else:
                clean[k] = v
        out.append(clean)
    return out


def _scored(system: Optional[str], days: int) -> pd.DataFrame:
    sig = da.signals(system=system, days=days)
    scores = attach_actor_metadata(actor_impact_table(sig), da.actors())
    if not scores.empty:
        scores["name"] = scores.apply(lambda r: r.get("name") or r["actor_slug"], axis=1)
        scores["category_label"] = scores["category"].map(lambda c: L.category(c) if c else "—")
    return scores


# ---------- routes ----------

@app.get("/api/health")
def health() -> dict:
    s = load_settings()
    return {"ok": True, "supabase_configured": s.has_supabase}


@app.get("/api/meta")
def meta() -> dict:
    return meta_payload()


@app.get("/api/actors")
def get_actors() -> dict:
    return {"actors": _records(da.actors())}


@app.get("/api/signals")
def get_signals(
    system: Optional[str] = None,
    days: int = Query(90, ge=1, le=365),
    actor: Optional[str] = None,
    signal_type: Optional[str] = None,   # v0.4.0 primary filter axis
    dimension: Optional[str] = None,
    source_kind: Optional[str] = None,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    sys = _norm_system(system)
    df = da.signals(system=sys, days=days)
    if df.empty:
        return {"signals": [], "count": 0}
    # Normalise legacy dimensions before filtering so a v0.3.0 key in the
    # query string still resolves to its v0.4.0 equivalent.
    df = df.copy()
    df["dimension"] = df["dimension"].map(L.normalise_dimension)
    df["signal_type_derived"] = df["dimension"].map(L.signal_type_for)
    if actor:
        df = df[df["actor_slug"] == actor]
    if signal_type:
        df = df[df["signal_type_derived"] == signal_type]
    if dimension:
        df = df[df["dimension"] == L.normalise_dimension(dimension)]
    if source_kind:
        df = df[df["source_kind"] == source_kind]
    if min_confidence > 0:
        df = df[df["confidence"].fillna(0) >= min_confidence]
    df = df.head(limit)
    # enrich with friendly labels
    actor_name = dict(zip(da.actors()["slug"], da.actors()["name"])) if not da.actors().empty else {}
    if not df.empty:
        df = df.assign(
            actor_name=df["actor_slug"].map(lambda s: actor_name.get(s, s)),
            dimension_label=df["dimension"].map(L.dimension),
            signal_type=df["signal_type_derived"],
            signal_type_label=df["signal_type_derived"].map(L.signal_type_label),
            source_kind_label=df["source_kind"].map(L.source_kind),
            cost_class=df["dimension"].map(L.cost_class),
        )
        df = df.drop(columns=["signal_type_derived"], errors="ignore")
    return {"signals": _records(df), "count": int(len(df))}


@app.get("/api/scores")
def get_scores(system: Optional[str] = None, days: int = Query(90, ge=1, le=365)) -> dict:
    sys = _norm_system(system)
    return {"scores": _records(_scored(sys, days))}


@app.get("/api/ecosystem")
def get_ecosystem(system: Optional[str] = None, days: int = Query(90, ge=1, le=365)) -> dict:
    sys = _norm_system(system)
    scores = _scored(sys, days)
    sig = da.signals(system=sys, days=days)
    actors_df = da.actors()

    # Normalise dimensions so legacy rows show under the right v0.4.0 keys.
    if not sig.empty and "dimension" in sig.columns:
        sig = sig.copy()
        sig["dimension"] = sig["dimension"].apply(L.normalise_dimension)

    # ---- Ehrenthal four-signal scheme: primary aggregation axis (v0.4.0). ----
    # We derive signal_type from the (normalised) dimension rather than the
    # Supabase column so rows that haven't been backfilled yet still bucket
    # correctly.
    signal_type_mix: list[dict] = []
    if not sig.empty:
        sig = sig.copy()
        sig["signal_type_derived"] = sig["dimension"].apply(L.signal_type_for)
        st = sig.groupby("signal_type_derived").size().reset_index(name="count")
        # Fixed display order so the chart is stable across runs.
        ORDER = ["legitimacy", "customer_cocreation", "community_ecosystem", "future_trajectory"]
        st["__order"] = st["signal_type_derived"].apply(
            lambda k: ORDER.index(k) if k in ORDER else len(ORDER)
        )
        st = st.sort_values(["__order", "signal_type_derived"])
        signal_type_mix = [
            {
                "signal_type": r["signal_type_derived"],
                "label": L.signal_type_label(r["signal_type_derived"]),
                "short_label": L.SIGNAL_TYPE_SHORT.get(r["signal_type_derived"], r["signal_type_derived"]),
                "color": L.SIGNAL_TYPE_COLOR.get(r["signal_type_derived"], "#888"),
                "count": int(r["count"]),
            }
            for _, r in st.iterrows()
            if r["signal_type_derived"]  # drop empty bucket if some row had no mapping
        ]

    # Dimension mix retained as the SECONDARY axis (drill-down). The web
    # frontend now groups dimensions by signal_type beneath the 4-bucket chart.
    dim_mix: list[dict] = []
    if not sig.empty:
        dm = sig.groupby("dimension").size().reset_index(name="count")
        dim_mix = [
            {
                "dimension": r["dimension"],
                "label": L.dimension(r["dimension"]),
                "signal_type": L.signal_type_for(r["dimension"]),
                "signal_type_label": L.signal_type_label(L.signal_type_for(r["dimension"])),
                "count": int(r["count"]),
                "cost_class": L.cost_class(r["dimension"]),
            }
            for _, r in dm.iterrows()
        ]

    # category mix (unchanged — orthogonal axis)
    cat_mix: list[dict] = []
    if not sig.empty and not actors_df.empty:
        merged = sig.merge(actors_df[["slug", "category"]].rename(columns={"slug": "actor_slug"}),
                           on="actor_slug", how="left")
        cm = merged.groupby("category").size().reset_index(name="count")
        cat_mix = [
            {"category": r["category"], "label": L.category(r["category"]) if r["category"] else "Unknown",
             "count": int(r["count"]), "color": L.CATEGORY_COLOR.get(r["category"], "#666")}
            for _, r in cm.iterrows()
        ]

    summary = ecosystem_summary(scores)
    if summary.get("top_actor") and not scores.empty:
        match = scores[scores["actor_slug"] == summary["top_actor"]]
        if not match.empty:
            summary["top_actor_name"] = match.iloc[0].get("name") or summary["top_actor"]

    return {
        "summary": summary,
        "actors_total": int(len(actors_df)),
        # Primary axis (v0.4.0 — Ehrenthal four-signal scheme).
        "signal_type_mix": signal_type_mix,
        # Secondary axis (sub-categories under each signal_type).
        "dimension_mix": sorted(dim_mix, key=lambda d: -d["count"]),
        # Orthogonal axis (actor category — unchanged).
        "category_mix": sorted(cat_mix, key=lambda d: -d["count"]),
        "top_actors": _records(scores.head(10)),
    }


@app.get("/api/signalling")
def get_signalling(system: Optional[str] = None, days: int = Query(90, ge=1, le=365)) -> dict:
    """Ehrenthal's research question made measurable: cheap talk vs costly signal."""
    sys = _norm_system(system)
    sig = da.signals(system=sys, days=days)
    scores = _scored(sys, days)

    cost_mix = {"high": 0, "medium": 0, "low": 0}
    channel_mix = {"capability": 0, "legitimacy": 0}
    if not sig.empty:
        for _, s in sig.iterrows():
            cost_mix[L.cost_class(s["dimension"])] = cost_mix.get(L.cost_class(s["dimension"]), 0) + 1
            ch = "capability" if s["dimension"] in L.CAPABILITY_DIMENSIONS else "legitimacy"
            channel_mix[ch] += 1

    total = sum(cost_mix.values()) or 1
    return {
        "cost_mix": cost_mix,
        "cost_mix_pct": {k: round(100 * v / total, 1) for k, v in cost_mix.items()},
        "channel_mix": channel_mix,
        "ecosystem_cheap_talk_ratio": round(cost_mix.get("low", 0) / total, 3),
        # per-actor: cheap_talk_ratio vs credibility — does cheap talk track costly signal?
        "actors": _records(scores[[
            "actor_slug", "name", "category_label", "impact", "credibility",
            "cheap_talk_ratio", "high_cost", "low_cost", "authority", "signal_count",
        ]]) if not scores.empty else [],
    }


@app.get("/api/coverage")
def get_coverage(system: Optional[str] = None, days: int = Query(90, ge=1, le=365)) -> dict:
    """B.3 — collection-breadth metric: signals/actor/week per source_kind."""
    sys = _norm_system(system)
    return coverage_payload(sys, days)


@app.get("/api/actor/{slug}")
def get_actor(slug: str, system: Optional[str] = None, days: int = Query(90, ge=1, le=365)) -> dict:
    sys = _norm_system(system)
    actors_df = da.actors()
    match = actors_df[actors_df["slug"] == slug] if not actors_df.empty else pd.DataFrame()
    if match.empty:
        raise HTTPException(status_code=404, detail=f"actor '{slug}' not found")
    actor = match.iloc[0].to_dict()

    sig = da.signals(system=sys, days=days)
    actor_sig = sig[sig["actor_slug"] == slug] if not sig.empty else pd.DataFrame()

    scores = _scored(sys, days)
    my = scores[scores["actor_slug"] == slug] if not scores.empty else pd.DataFrame()
    score = _records(my)[0] if not my.empty else None

    # peer rank within category
    rank = None
    peers_total = None
    if score and not scores.empty:
        cat = actor.get("category")
        peers = scores[scores["category"] == cat].sort_values("impact", ascending=False).reset_index(drop=True)
        if not peers.empty:
            idx = peers.index[peers["actor_slug"] == slug].tolist()
            if idx:
                rank = int(idx[0]) + 1
                peers_total = int(len(peers))

    # signal mix + enrich
    if not actor_sig.empty:
        actor_sig = actor_sig.assign(
            dimension_label=actor_sig["dimension"].map(L.dimension),
            source_kind_label=actor_sig["source_kind"].map(L.source_kind),
            cost_class=actor_sig["dimension"].map(L.cost_class),
        )
    mix = []
    if not actor_sig.empty:
        m = actor_sig.groupby("dimension").size().reset_index(name="count")
        mix = [{"dimension": r["dimension"], "label": L.dimension(r["dimension"]), "count": int(r["count"])}
               for _, r in m.iterrows()]

    return {
        "actor": {**actor, "category_label": L.category(actor.get("category", "")) if actor.get("category") else None},
        "score": score,
        "rank_in_category": rank,
        "peers_in_category": peers_total,
        "signal_mix": sorted(mix, key=lambda d: -d["count"]),
        "signals": _records(actor_sig.sort_values("inserted_at", ascending=False)),
    }


@app.get("/api/compare")
def get_compare(days: int = Query(90, ge=1, le=365)) -> dict:
    """System A vs System B head-to-head."""
    out: dict[str, Any] = {}
    runs_all = da.runs(system=None, days=days)
    sig_all = da.signals(system=None, days=days)
    tok_all = da.token_usage(system=None, days=days)
    actors_df = da.actors()
    actor_name = dict(zip(actors_df["slug"], actors_df["name"])) if not actors_df.empty else {}

    # v0.4.36 — extract tool_status + model from config_snapshot so we
    # can present a tool-status breakdown alongside the comparison.
    # Hermes records both in v0.4.36+; older runs without the keys count
    # as "unknown" and are surfaced separately so §3.5 can exclude them.
    def _cfg(row: dict, key: str, default: str = "unknown") -> str:
        cfg = row.get("config_snapshot") if isinstance(row, dict) else None
        if isinstance(cfg, dict) and cfg.get(key):
            return str(cfg.get(key))
        return default

    per_system = {}
    for sys_ in ("masfactory", "hermes"):
        s_runs = runs_all[runs_all["system"] == sys_] if not runs_all.empty else pd.DataFrame()
        s_sig = sig_all[sig_all["system"] == sys_] if ("system" in sig_all.columns and not sig_all.empty) else pd.DataFrame()
        s_tok = tok_all[tok_all["system"] == sys_] if not tok_all.empty else pd.DataFrame()
        in_tok = int(s_tok["input_tokens"].sum()) if not s_tok.empty else 0
        out_tok = int(s_tok["output_tokens"].sum()) if not s_tok.empty else 0
        n_sig = int(len(s_sig))

        tool_status_counts: dict[str, int] = {}
        model_counts: dict[str, int] = {}
        if not s_runs.empty and "config_snapshot" in s_runs.columns:
            for _, r in s_runs.iterrows():
                ts = _cfg(r.to_dict(), "tool_status")
                mdl = _cfg(r.to_dict(), "model")
                tool_status_counts[ts] = tool_status_counts.get(ts, 0) + 1
                model_counts[mdl] = model_counts.get(mdl, 0) + 1

        per_system[sys_] = {
            "label": L.system_label(sys_),
            "runs": int(len(s_runs)),
            "runs_ok": int((s_runs["status"] == "ok").sum()) if not s_runs.empty else 0,
            "runs_error": int((s_runs["status"] == "error").sum()) if not s_runs.empty else 0,
            "signals": n_sig,
            "actors": int(s_sig["actor_slug"].nunique()) if not s_sig.empty else 0,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "signals_per_1k_tokens": round(n_sig / max(1, (in_tok + out_tok) / 1000), 2) if (in_tok + out_tok) else None,
            # v0.4.36 transparency surfaces:
            "tool_status_counts": tool_status_counts,
            "model_counts": model_counts,
        }

    # per-actor impact agreement
    def _impact_map(sys_):
        s = sig_all[sig_all["system"] == sys_] if ("system" in sig_all.columns and not sig_all.empty) else pd.DataFrame()
        sc = actor_impact_table(s)
        return dict(zip(sc["actor_slug"], sc["impact"])) if not sc.empty else {}

    a_map, b_map = _impact_map("masfactory"), _impact_map("hermes")
    agreement = []
    for slug in sorted(set(a_map) | set(b_map)):
        ai, bi = float(a_map.get(slug, 0.0)), float(b_map.get(slug, 0.0))
        if ai == 0 and bi == 0:
            continue
        status = "both" if (ai > 0 and bi > 0) else ("only_a" if ai > 0 else "only_b")
        agreement.append({"actor_slug": slug, "name": actor_name.get(slug, slug),
                          "system_a_impact": round(ai, 2), "system_b_impact": round(bi, 2), "status": status})

    out["per_system"] = per_system
    out["agreement"] = sorted(agreement, key=lambda r: -r["system_a_impact"])
    out["agreement_counts"] = {
        "both": sum(1 for r in agreement if r["status"] == "both"),
        "only_a": sum(1 for r in agreement if r["status"] == "only_a"),
        "only_b": sum(1 for r in agreement if r["status"] == "only_b"),
    }
    return out


@app.get("/api/knowledge-graph")
def get_kg(
    system: Optional[str] = None,
    days: int = Query(90, ge=1, le=365),
    threshold: int = Query(2, ge=1, le=9),
    # v0.4.40 — additive feature gates. Default off so any pre-v0.4.40
    # frontend sees the exact same response shape it always did.
    include_taxonomy: bool = Query(False, description="Add the 4 signal_type nodes + taxonomy/volume edges (v0.4.40)"),
    include_semantic: bool = Query(False, description="Add pgvector-cosine actor↔actor semantic edges (v0.4.40)"),
    semantic_threshold: float = Query(0.85, ge=0.0, le=1.0, description="Min cosine similarity for semantic edges (v0.4.40)"),
) -> dict:
    sys = _norm_system(system)
    sig_df = da.signals(system=sys, days=days)
    if include_semantic and not sig_df.empty:
        emb_df = da.signal_embeddings(system=sys, days=days)
        if not emb_df.empty:
            sig_df = sig_df.merge(
                emb_df[["id", "embedding"]], on="id", how="left",
            )
    return build_graph_json(
        sig_df,
        da.actors(),
        shared_dim_threshold=threshold,
        include_taxonomy=include_taxonomy,
        include_semantic=include_semantic,
        semantic_threshold=semantic_threshold,
    )


@app.get("/api/industry-news")
def get_industry_news(days: int = Query(30, ge=1, le=365),
                      limit: int = Query(100, ge=1, le=500)) -> dict:
    """v0.4.3 — worldwide quantum news (not actor-attributed). Backing
    table public.industry_news is populated by the industry-news cron job.
    Read-only."""
    try:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = (da.client().table("industry_news")
                .select("id,source_url,source_name,title,summary,published_at,fetched_at")
                .gte("fetched_at", since)
                .order("published_at", desc=True)
                .limit(limit)
                .execute()).data or []
        return {"items": rows, "count": len(rows), "days": days}
    except Exception as exc:
        return {"items": [], "count": 0, "error": str(exc)}


@app.get("/api/reports")
def get_reports(kind: Optional[str] = None, period: Optional[str] = None, file: Optional[str] = None) -> dict:
    if period and file and kind:
        body = R.get_report(kind, period, file)
        if body is None:
            raise HTTPException(status_code=404, detail="report not found")
        return {"kind": kind, "period": period, "file": file, "markdown": body}
    return {"reports": R.list_reports(kind)}


# ---------------------------------------------------------------------------
# signal_flags — Workflow B from docs/wrong-signals-strategy.md
# Users (Anna; supervisor; reviewers) flag wrong signals; the cron's
# Persistence step refuses to re-insert any flagged (actor, url, hash)
# tuple. The aggregate per-source / per-system / per-actor-category
# wrong-signal rate is a thesis-citable quality metric (Chapter 3.5).
# ---------------------------------------------------------------------------

FlagReason = Literal[
    "wrong_actor",       # the actor_slug attribution is incorrect
    "off_topic",         # signal not actually about quantum
    "wrong_dimension",   # dimension/signal_type mis-classified
    "low_quality",       # generic / boilerplate, no substance
    "duplicate",         # same event already in the corpus
    "other",
]


class FlagPayload(BaseModel):
    signal_id: str = Field(min_length=8, description="UUID of the signal being flagged.")
    reason: FlagReason
    note: Optional[str] = Field(default=None, max_length=2000)


@app.post("/api/signal-flags")
def post_signal_flag(payload: FlagPayload) -> dict:
    """Record a wrong-signal flag. Idempotent on (signal_id, reason)."""
    try:
        client = da.client()
    except Exception:
        raise HTTPException(status_code=503, detail="Supabase unavailable")

    # Confirm the signal exists — return 404 instead of silently creating
    # an orphan flag (which the FK cascade would later reject anyway).
    sig = client.table("signals").select("id").eq("id", payload.signal_id).limit(1).execute()
    if not sig.data:
        raise HTTPException(status_code=404, detail="signal_id not found")

    row = {
        "signal_id": payload.signal_id,
        "reason": payload.reason,
        "note": payload.note,
    }
    try:
        resp = client.table("signal_flags").insert(row).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"flag insert failed: {exc}")
    return {"flag": (resp.data or [{}])[0], "ok": True}


@app.get("/api/signal-flags")
def get_signal_flags(
    signal_id: Optional[str] = None,
    summary: bool = False,
    days: int = Query(90, ge=1, le=365),
) -> dict:
    """List flags for a specific signal, OR aggregate stats across the window.

    Without ?signal_id and without ?summary=true: returns recent flags.
    With ?signal_id=...: returns flags for that signal.
    With ?summary=true: returns aggregate { by_reason, by_system, by_actor_category, total }.
    """
    try:
        client = da.client()
    except Exception:
        return {"flags": [], "error": "Supabase unavailable"}

    if signal_id:
        try:
            resp = client.table("signal_flags").select("*").eq("signal_id", signal_id).execute()
        except Exception:
            return {"flags": []}
        return {"flags": resp.data or []}

    if summary:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            flags = client.table("signal_flags").select(
                "id,signal_id,reason,flagged_at"
            ).gte("flagged_at", since).execute().data or []
        except Exception:
            flags = []
        if not flags:
            return {"total": 0, "by_reason": {}, "by_system": {}, "by_actor_category": {}, "days": days}

        # Join to signals → actors for per-system + per-category aggregates.
        sig_ids = list({f["signal_id"] for f in flags})
        sigs: list[dict] = []
        for i in range(0, len(sig_ids), 100):
            chunk = sig_ids[i:i + 100]
            r = client.table("signals").select("id,system,actor_slug").in_("id", chunk).execute()
            sigs.extend(r.data or [])
        sig_by_id = {s["id"]: s for s in sigs}

        actors = da.actors()
        cat_by_slug = {}
        if not actors.empty:
            cat_by_slug = dict(zip(actors["slug"], actors["category"]))

        by_reason: dict[str, int] = {}
        by_system: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        for f in flags:
            by_reason[f["reason"]] = by_reason.get(f["reason"], 0) + 1
            s = sig_by_id.get(f["signal_id"], {})
            sys_ = s.get("system") or "unknown"
            by_system[sys_] = by_system.get(sys_, 0) + 1
            cat = cat_by_slug.get(s.get("actor_slug"), "unknown")
            by_cat[cat] = by_cat.get(cat, 0) + 1

        return {
            "total": len(flags),
            "days": days,
            "by_reason": by_reason,
            "by_system": by_system,
            "by_actor_category": by_cat,
        }

    # Default: most recent 50 flags.
    try:
        resp = (client.table("signal_flags")
                .select("id,signal_id,reason,note,flagged_at")
                .order("flagged_at", desc=True)
                .limit(50)
                .execute())
    except Exception:
        return {"flags": []}
    return {"flags": resp.data or []}


# ---------------------------------------------------------------------------
# v0.4.37 hotfix — editorial training layer route registration
# This block was lost during the original v0.4.37 PR (linter race condition
# clobbered the Edit). The /api/manual-signals and /api/sources CRUD
# endpoints are implemented in api_app/training.py; this just registers
# them with FastAPI. Same auth model as the rest of the API: trust Caddy
# basic-auth — "Anna only" by deployment.
# ---------------------------------------------------------------------------


@app.get("/api/manual-signals")
def list_manual_signals_route(limit: int = Query(500, ge=1, le=5000)) -> dict:
    return {"manual_signals": T.list_manual_signals(limit=limit)}


@app.get("/api/manual-signals/{signal_id}")
def get_manual_signal_route(signal_id: str) -> dict:
    row = T.get_manual_signal(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="manual_signal not found")
    return {"manual_signal": row}


@app.post("/api/manual-signals")
def create_manual_signal_route(payload: T.ManualSignalIn) -> dict:
    return {"manual_signal": T.create_manual_signal(payload), "ok": True}


@app.patch("/api/manual-signals/{signal_id}")
def patch_manual_signal_route(signal_id: str, payload: T.ManualSignalPatch) -> dict:
    return {"manual_signal": T.patch_manual_signal(signal_id, payload), "ok": True}


@app.delete("/api/manual-signals/{signal_id}")
def delete_manual_signal_route(signal_id: str) -> dict:
    T.delete_manual_signal(signal_id)
    return {"ok": True}


@app.get("/api/sources")
def list_sources_route(
    enabled: Optional[bool] = None,
    limit: int = Query(500, ge=1, le=5000),
) -> dict:
    return {"sources": T.list_sources(enabled=enabled, limit=limit)}


@app.get("/api/sources/{source_id}")
def get_source_route(source_id: str) -> dict:
    row = T.get_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="signal_source not found")
    return {"source": row}


@app.post("/api/sources")
def create_source_route(payload: T.SignalSourceIn) -> dict:
    return {"source": T.create_source(payload), "ok": True}


@app.patch("/api/sources/{source_id}")
def patch_source_route(source_id: str, payload: T.SignalSourcePatch) -> dict:
    return {"source": T.patch_source(source_id, payload), "ok": True}


@app.delete("/api/sources/{source_id}")
def delete_source_route(source_id: str) -> dict:
    T.delete_source(source_id)
    return {"ok": True}

