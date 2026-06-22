"""Read-only Supabase queries for report generation.

The reports container only reads; it never writes to Supabase. Token usage
that *the report itself* burns is recorded in the report's audit folder,
not in the Supabase `token_usage` table (that table is for the upstream
systems' runs, keeping cross-system comparison clean).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from supabase import Client, create_client

from .config import Settings


SystemName = Literal["masfactory", "hermes"]


class SupabaseReader:
    def __init__(self, settings: Settings):
        if not settings.has_supabase:
            raise RuntimeError("Supabase credentials missing")
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_key)

    # ---------- low-level fetches ----------

    def runs_in_window(self, *, system: SystemName | None, since: datetime, until: datetime) -> list[dict]:
        q = (
            self._client.table("runs")
            .select("id,system,status,started_at,finished_at,actor_slugs,error_message")
            .gte("started_at", since.isoformat())
            .lte("started_at", until.isoformat())
            .order("started_at", desc=False)
        )
        if system:
            q = q.eq("system", system)
        return q.execute().data or []

    def signals_for_runs(self, run_ids: list[str]) -> list[dict]:
        if not run_ids:
            return []
        return (
            self._client.table("signals")
            .select(
                # v0.4.27 — added the v0.4.0 (signal_type) and v0.4.19 (defense
                # flags) and v0.4.24 (sentiment) columns the report now uses.
                "run_id,actor_slug,source_kind,source_url,title,summary,"
                "evidence_quote,dimension,signal_type,is_technical,confidence,"
                "inserted_at,stakeholder,defense_engagement,defense_ambivalence,"
                "sentiment_score,sentiment_label"
            )
            .in_("run_id", run_ids)
            .order("inserted_at", desc=False)
            .execute()
            .data
            or []
        )

    def token_usage_for_runs(self, run_ids: list[str]) -> list[dict]:
        if not run_ids:
            return []
        return (
            self._client.table("token_usage")
            .select("run_id,node_name,model_name,input_tokens,output_tokens,calls")
            .in_("run_id", run_ids)
            .execute()
            .data
            or []
        )

    def actors(self) -> list[dict]:
        return self._client.table("actors").select("slug,name,category,homepage").execute().data or []

    # ---------- aggregate views used by report generators ----------

    def daily_snapshot(self, *, system: SystemName, window_hours: int = 24) -> dict[str, Any]:
        until = datetime.now(timezone.utc)
        since = until - timedelta(hours=window_hours)
        runs = self.runs_in_window(system=system, since=since, until=until)
        run_ids = [r["id"] for r in runs]
        signals = self.signals_for_runs(run_ids)
        tokens = self.token_usage_for_runs(run_ids)

        actors_by_slug = {a["slug"]: a for a in self.actors()}
        return {
            "system": system,
            "window_since": since.isoformat(),
            "window_until": until.isoformat(),
            "runs": runs,
            "signals": signals,
            "tokens": tokens,
            "actors_by_slug": actors_by_slug,
            "summary": _summarise(runs, signals, tokens, actors_by_slug),
        }

    def weekly_snapshot(self, *, system: SystemName) -> dict[str, Any]:
        return self.daily_snapshot(system=system, window_hours=24 * 7)

    def both_systems_summary(self, *, window_hours: int) -> dict[str, Any]:
        until = datetime.now(timezone.utc)
        since = until - timedelta(hours=window_hours)
        all_runs = self.runs_in_window(system=None, since=since, until=until)
        run_ids = [r["id"] for r in all_runs]
        all_signals = self.signals_for_runs(run_ids)
        all_tokens = self.token_usage_for_runs(run_ids)
        actors_by_slug = {a["slug"]: a for a in self.actors()}

        per_system: dict[str, dict[str, Any]] = {}
        for sys_ in ("masfactory", "hermes"):
            runs_s = [r for r in all_runs if r["system"] == sys_]
            run_ids_s = [r["id"] for r in runs_s]
            sigs_s = [s for s in all_signals if s["run_id"] in run_ids_s]
            toks_s = [t for t in all_tokens if t["run_id"] in run_ids_s]
            per_system[sys_] = _summarise(runs_s, sigs_s, toks_s, actors_by_slug)

        return {
            "window_since": since.isoformat(),
            "window_until": until.isoformat(),
            "per_system": per_system,
            "actor_count": len(actors_by_slug),
        }


def _summarise(runs: list[dict], signals: list[dict], tokens: list[dict], actors_by_slug: dict) -> dict[str, Any]:
    by_actor: dict[str, list[dict]] = defaultdict(list)
    for s in signals:
        by_actor[s["actor_slug"]].append(s)

    dim_counter = Counter(s["dimension"] for s in signals)
    tech_counter = Counter(("technical" if s["is_technical"] else "non-technical") for s in signals)
    actor_signal_counts = {slug: len(items) for slug, items in by_actor.items()}

    # v0.4.27 — the four-Ehrenthal axis (signal_type), sentiment label,
    # defense flags, source_kind distribution, and stakeholder lens.
    # All NULL-safe: rows from pre-v0.4.0 may not have signal_type,
    # pre-v0.4.24 rows have no sentiment, etc.
    sig_type_counter = Counter(s.get("signal_type") or "unknown" for s in signals)
    sentiment_counter = Counter(s.get("sentiment_label") or "n/a" for s in signals)
    source_counter = Counter(s.get("source_kind") or "unknown" for s in signals)
    stakeholder_counter = Counter(s.get("stakeholder") or "n/a" for s in signals)
    defense_engagement = sum(1 for s in signals if s.get("defense_engagement"))
    defense_ambivalence = sum(1 for s in signals if s.get("defense_ambivalence"))

    # Actors with zero signals in this window — the coverage gap.
    actors_with_signals_set = set(by_actor.keys())
    actors_no_signals = [
        slug for slug in actors_by_slug.keys()
        if slug not in actors_with_signals_set
    ]

    token_total_in = sum(int(t.get("input_tokens") or 0) for t in tokens)
    token_total_out = sum(int(t.get("output_tokens") or 0) for t in tokens)
    token_total_calls = sum(int(t.get("calls") or 0) for t in tokens)

    return {
        "run_count": len(runs),
        "run_ok": sum(1 for r in runs if r.get("status") == "ok"),
        "run_error": sum(1 for r in runs if r.get("status") == "error"),
        "signal_count": len(signals),
        "by_dimension": dict(dim_counter),
        "by_signal_type": dict(sig_type_counter),
        "by_sentiment": dict(sentiment_counter),
        "by_source_kind": dict(source_counter),
        "by_stakeholder": dict(stakeholder_counter),
        "by_technical": dict(tech_counter),
        "defense_engagement_count": defense_engagement,
        "defense_ambivalence_count": defense_ambivalence,
        "actors_with_signals": len(by_actor),
        "actors_total": len(actors_by_slug),
        # v0.4.27 — surface the coverage gap so the report can name it.
        "actors_no_signals_count": len(actors_no_signals),
        "actors_no_signals_sample": actors_no_signals[:15],
        "top_actors_by_signal_count": sorted(actor_signal_counts.items(), key=lambda kv: kv[1], reverse=True)[:10],
        "total_input_tokens": token_total_in,
        "total_output_tokens": token_total_out,
        "total_calls": token_total_calls,
    }
