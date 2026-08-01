"""Thin wrapper around supabase-py for the rows this system writes.

All writes are idempotent — the cron schedule means the same run can fire
twice (e.g. after a transient network blip on the host). `signals` carries a
unique constraint on (actor_slug, source_url, content_hash, system) so
duplicate inserts are silently ignored at the DB level. `system` has been part
of that key since v0.5.0: System A and System B each record their OWN copy of
a signal both of them found, because suppressing the second one would cap
whichever system happened to run later and confound the A-vs-B comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client, create_client

from ..config import Settings


# Producer name this module writes under. Part of the signals uniqueness key
# and the scope for semantic dedup, so it is named once rather than repeated.
SYSTEM = "masfactory"


@dataclass
class RunRow:
    id: str
    system: str = SYSTEM
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SignalRow:
    run_id: str
    actor_slug: str
    source_kind: str
    source_url: str
    title: str
    summary: str
    evidence_quote: str
    dimension: str
    is_technical: bool
    confidence: float
    content_hash: str
    observed_at: Optional[datetime] = None
    # 768-dim BGE embedding (see masfactory_system/embedding.py). Optional —
    # left None when MASF_EMBEDDINGS is off, which writes a SQL NULL into the
    # pgvector column. Downstream similarity queries can `where embedding is
    # not null` to skip un-embedded rows.
    embedding: Optional[list[float]] = None
    # Ehrenthal et al. (2026) top-level signal type. The Persistence node
    # fills this from dimension via classification.signal_type_for_dimension()
    # if the Classifier didn't emit it directly — so older code paths still
    # produce well-typed rows.
    signal_type: Optional[str] = None
    # v0.4.24 — VADER compound sentiment (Hutto & Gilbert 2014). Both fields
    # populated together or both None. Disabled with MASF_SENTIMENT=0.
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    # v0.4.36 — defense flags now first-class on SignalRow so the persister
    # writes the computed value rather than defaulting to False via getattr.
    # Computed in agents/persistence.py as (LLM-judgement OR keyword-backstop),
    # symmetric with System B (see masfactory_system/defense_keywords.py).
    defense_engagement: bool = False
    defense_ambivalence: bool = False


class SupabaseStore:
    def __init__(self, settings: Settings):
        if not settings.has_supabase:
            raise RuntimeError("Supabase credentials missing — set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_key)

    # ---------- actors ----------

    # Columns that come from actors.yaml and SHOULD be refreshed on each run.
    _ACTOR_STATIC_COLS = ("slug", "name", "category", "homepage")
    # Columns that Anna may edit by hand in Supabase — never overwritten by YAML.
    _ACTOR_USER_EDITABLE = ("arxiv_query", "notes")

    def upsert_actors(self, actors: list[dict[str, Any]]) -> None:
        """Seed new actors from YAML, refresh static columns on existing ones.

        User-editable columns (`arxiv_query`, `notes`) come from YAML *only*
        when an actor is being inserted for the first time. For actors that
        already exist in Supabase, those columns are preserved so Anna can
        edit them directly in the Supabase Table editor without her changes
        being clobbered by the next cron tick.
        """
        if not actors:
            return

        existing_slugs = {
            row["slug"]
            for row in (self._client.table("actors").select("slug").execute().data or [])
        }

        payload: list[dict[str, Any]] = []
        for a in actors:
            if a["slug"] in existing_slugs:
                # Existing actor: refresh only static columns.
                payload.append({k: a.get(k) for k in self._ACTOR_STATIC_COLS})
            else:
                # New actor: insert everything we have from YAML.
                payload.append(a)

        if payload:
            self._client.table("actors").upsert(payload, on_conflict="slug").execute()

    # ---------- runs ----------

    def start_run(self, *, actor_slugs: list[str], config_snapshot: dict[str, Any]) -> str:
        payload = {
            "system": SYSTEM,
            "status": "running",
            "actor_slugs": actor_slugs,
            "config_snapshot": config_snapshot,
        }
        resp = self._client.table("runs").insert(payload).execute()
        return resp.data[0]["id"]

    def finish_run(self, run_id: str, *, status: str = "ok", error_message: str | None = None) -> None:
        self._client.table("runs").update(
            {
                "status": status,
                "error_message": error_message,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", run_id).execute()

    # ---------- signals ----------

    def insert_signals(self, signals: list[SignalRow]) -> int:
        if not signals:
            return 0
        rows = [self._signal_to_row(s) for s in signals]
        resp = (
            self._client.table("signals")
            # v0.5.0 — per-system dedup: `system` in the conflict key so System A
            # records its own findings even when System B already found the same
            # signal (and vice versa). Matches schema.sql's 4-column unique key.
            .upsert(rows, on_conflict="actor_slug,source_url,content_hash,system", ignore_duplicates=True)
            .execute()
        )
        return len(resp.data or [])

    @staticmethod
    def _signal_to_row(s: SignalRow) -> dict[str, Any]:
        row: dict[str, Any] = {
            "run_id": s.run_id,
            "actor_slug": s.actor_slug,
            "system": SYSTEM,
            "source_kind": s.source_kind,
            "source_url": s.source_url,
            "title": s.title,
            "summary": s.summary,
            "evidence_quote": s.evidence_quote,
            "dimension": s.dimension,
            "is_technical": s.is_technical,
            "confidence": s.confidence,
            "content_hash": s.content_hash,
            "observed_at": s.observed_at.isoformat() if s.observed_at else None,
            # v0.4.19: defense flags overlaid on the Ehrenthal four.
            "defense_engagement": bool(getattr(s, "defense_engagement", False)),
            "defense_ambivalence": bool(getattr(s, "defense_ambivalence", False)),
        }
        if s.embedding is not None:
            row["embedding"] = s.embedding
        if s.signal_type is not None:
            row["signal_type"] = s.signal_type
        if s.sentiment_score is not None:
            row["sentiment_score"] = s.sentiment_score
        if s.sentiment_label is not None:
            row["sentiment_label"] = s.sentiment_label
        return row

    # ---------- signal_flags (Workflow B) ----------

    def gold_examples(self, *, limit_per_dimension: int = 2) -> list[dict]:
        """v0.4.2 — return Anna's hand-labelled positive examples for the
        Classifier prompt. Reads signal_flags WHERE reason='correct_example'
        joined to signals, returns the top-N most recent per dimension so
        the few-shot block stays diverse across the 21 dimensions.

        Used by classification.few_shot_examples() to dynamically build the
        Classifier's prompt block. Empty list = no examples yet → Classifier
        runs prompt-only (same as v0.4.1)."""
        try:
            flags = (self._client.table("signal_flags")
                     .select("signal_id,note,flagged_at")
                     .eq("reason", "correct_example")
                     .order("flagged_at", desc=True)
                     .limit(200)
                     .execute()).data or []
            if not flags:
                return []
            ids = list({f["signal_id"] for f in flags})
            note_by_id = {f["signal_id"]: f.get("note") or "" for f in flags}
            by_dim: dict[str, list[dict]] = {}
            for i in range(0, len(ids), 100):
                chunk = ids[i:i + 100]
                sigs = (self._client.table("signals")
                        .select("id,actor_slug,dimension,signal_type,evidence_quote,"
                                "title,confidence")
                        .in_("id", chunk)
                        .execute()).data or []
                for s in sigs:
                    dim = s.get("dimension") or "unknown"
                    bucket = by_dim.setdefault(dim, [])
                    if len(bucket) < limit_per_dimension:
                        bucket.append({**s, "anna_note": note_by_id.get(s["id"], "")})
            # Flatten in a deterministic order so the prompt is stable run-to-run.
            return [s for dim in sorted(by_dim) for s in by_dim[dim]]
        except Exception:
            return []

    def flagged_tuples(self, *, days_back: int = 365) -> set[tuple[str, str]]:
        """Return the set of (actor_slug, source_url) tuples that the user
        has flagged as wrong via /api/signal-flags. Persistence calls this
        before insert and skips any candidate whose tuple is flagged.

        Lookback is generous (1 year by default) so a once-flagged signal
        stays out of the corpus even if the original cron tick that produced
        it falls out of any rolling window.

        Soft-fails to an empty set on any error — the cron should never
        crash because the flags table isn't reachable.
        """
        try:
            from datetime import datetime, timedelta, timezone
            since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
            flags = (self._client.table("signal_flags")
                     .select("signal_id")
                     .gte("flagged_at", since)
                     .execute()).data or []
            if not flags:
                return set()
            ids = list({f["signal_id"] for f in flags})
            tuples: set[tuple[str, str]] = set()
            for i in range(0, len(ids), 100):
                chunk = ids[i:i + 100]
                sigs = (self._client.table("signals")
                        .select("actor_slug,source_url")
                        .in_("id", chunk)
                        .execute()).data or []
                for s in sigs:
                    if s.get("actor_slug") and s.get("source_url"):
                        tuples.add((s["actor_slug"], s["source_url"]))
            return tuples
        except Exception:
            return set()

    # ---------- semantic dedup (pgvector cosine via RPC) ----------

    def find_similar_signal(
        self,
        *,
        actor_slug: str,
        embedding: list[float],
        days_back: int = 30,
        system: Optional[str] = SYSTEM,
    ) -> Optional[dict[str, Any]]:
        """Return the single nearest existing signal for this actor, or None.

        Calls the `public.find_similar_signals` Postgres function (defined
        in schema.sql) which performs the cosine-distance lookup against
        the pgvector index. Returns `{id, title, evidence_quote,
        source_url, system, similarity, inserted_at}` for the closest hit,
        or None if there are no embedded signals for this actor in the
        time window.

        v0.5.3 — `system` scopes the search to ONE producer and defaults to
        this system's own rows. Before that the search covered the whole
        corpus, so a near-identical row already written by System B made
        System A drop its own record of the same event. That contradicted the
        v0.5.0 uniqueness key, which deliberately includes `system` so each
        architecture records its own findings. Deduplication is a
        within-system concern; cross-system overlap is measured by
        eval_app/metrics/inter_system_agreement.py, not deleted here.
        Pass system=None to search every producer deliberately.

        Defensive: any Supabase / network error returns None — the caller
        treats None as "no near-duplicate found" and proceeds with insert
        (a soft-fail that biases toward recall, matching the thesis's
        recall-over-precision stance throughout the pipeline). That also
        makes the deploy order of this change safe: an image calling the
        five-argument form against a database still on the four-argument
        function fails open rather than suppressing signals.
        """
        try:
            resp = self._client.rpc(
                "find_similar_signals",
                {
                    "p_actor_slug": actor_slug,
                    "p_query_embedding": embedding,
                    "p_days_back": int(days_back),
                    "p_limit": 1,
                    "p_system": system,
                },
            ).execute()
        except Exception:
            return None
        data = resp.data or []
        if not data:
            return None
        return data[0]

    # ---------- token usage ----------

    def record_token_usage(self, run_id: str, entries: list[dict[str, Any]]) -> None:
        if not entries:
            return
        rows = [{**e, "run_id": run_id} for e in entries]
        self._client.table("token_usage").insert(rows).execute()

    # ---------- audit ----------

    def append_audit(self, run_id: str, node_name: str, payload: dict[str, Any]) -> None:
        self._client.table("audit_log").insert(
            {"run_id": run_id, "node_name": node_name, "payload": payload}
        ).execute()
