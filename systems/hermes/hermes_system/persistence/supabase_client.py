"""Supabase writer for System B.

Independent of System A's client (the two systems must not share code beyond
the data contract) but writes to the *same* tables. Use `system='hermes'` on
the `runs` row so cross-system queries stay clean.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client, create_client

from ..config import Settings


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
    # 768d BGE embedding — see hermes_system/embedding.py. Optional, gated by
    # HRM_EMBEDDINGS=1. None → NULL in the pgvector column.
    embedding: Optional[list[float]] = None


class SupabaseStore:
    def __init__(self, settings: Settings):
        if not settings.has_supabase:
            raise RuntimeError("Supabase credentials missing — set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_key)

    # ---------- actors ----------

    _ACTOR_STATIC_COLS = ("slug", "name", "category", "homepage")
    _ACTOR_USER_EDITABLE = ("arxiv_query", "notes")

    def upsert_actors(self, actors: list[dict[str, Any]]) -> None:
        """Seed new actors from YAML; preserve user-editable columns on existing rows.

        See systems/masfactory/.../supabase_client.py upsert_actors for full
        rationale. Same behaviour here so both systems stay aligned.
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
                payload.append({k: a.get(k) for k in self._ACTOR_STATIC_COLS})
            else:
                payload.append(a)

        if payload:
            self._client.table("actors").upsert(payload, on_conflict="slug").execute()

    # ---------- runs ----------

    def start_run(self, *, actor_slugs: list[str], config_snapshot: dict[str, Any]) -> str:
        payload = {
            "system": "hermes",
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

    def derive_signal_rows(
        self, run_id: str, raw_signals: list[dict[str, Any]]
    ) -> list[SignalRow]:
        """Compose SignalRows with optional embedding + optional semantic dedup.

        Note: was a @staticmethod prior to the dedup landing; now an
        instance method because the dedup needs `self._client` to query
        the existing corpus. Callers in runner.py already invoke as a
        method on the instance, so the API change is source-compatible.
        """
        # Local imports — keep the embedding hooks lazy so this module is
        # cheap to import in environments without fastembed installed.
        import os as _os
        from ..embedding import compose_signal_text, embed_text, is_enabled as embeddings_enabled

        embed_on = embeddings_enabled()

        sem_on = _os.environ.get("HRM_SEMANTIC_DEDUP", "").strip().lower() in (
            "1", "true", "yes", "on"
        )
        try:
            sem_threshold = float(_os.environ.get("HRM_SEMANTIC_DEDUP_THRESHOLD", "0.92"))
        except (TypeError, ValueError):
            sem_threshold = 0.92
        try:
            sem_days = int(_os.environ.get("HRM_SEMANTIC_DEDUP_DAYS", "30"))
        except (TypeError, ValueError):
            sem_days = 30
        sem_threshold = max(0.5, min(0.999, sem_threshold))
        sem_days = max(1, min(365, sem_days))
        sem_active = sem_on and embed_on

        rows: list[SignalRow] = []
        for s in raw_signals:
            evidence = s.get("evidence_quote") or ""
            content_hash = hashlib.sha256(
                f"{s.get('actor_slug')}|{s.get('source_url')}|{evidence}".encode("utf-8")
            ).hexdigest()
            emb = embed_text(compose_signal_text(s)) if embed_on else None

            if sem_active and emb is not None:
                neighbour = self.find_similar_signal(
                    actor_slug=s["actor_slug"],
                    embedding=emb,
                    days_back=sem_days,
                )
                if neighbour and float(neighbour.get("similarity", 0.0)) >= sem_threshold:
                    # Drop this signal — its embedding is already in the
                    # corpus. Hermes' single-loop runner doesn't have a
                    # graph-level audit folder for per-row dedup logs;
                    # the run-level audit ('actor_<slug>.json') already
                    # records the transcript so the dedup decision is
                    # traceable via Supabase (the matched signal's id is
                    # what we'd point at).
                    continue

            rows.append(
                SignalRow(
                    run_id=run_id,
                    actor_slug=s["actor_slug"],
                    source_kind=s["source_kind"],
                    source_url=s["source_url"],
                    title=s.get("title", ""),
                    summary=s.get("summary", ""),
                    evidence_quote=evidence,
                    dimension=s["dimension"],
                    is_technical=bool(s["is_technical"]),
                    confidence=float(s.get("confidence", 0.0)),
                    content_hash=content_hash,
                    embedding=emb,
                )
            )
        return rows

    def find_similar_signal(
        self,
        *,
        actor_slug: str,
        embedding: list[float],
        days_back: int = 30,
    ) -> Optional[dict[str, Any]]:
        """Nearest existing signal for this actor via pgvector cosine RPC.

        Mirrors systems/masfactory/.../supabase_client.py — same RPC, same
        return shape. Soft-fails to None on any error so the cron stays
        running even if the function is missing or Supabase is flaky.
        """
        try:
            resp = self._client.rpc(
                "find_similar_signals",
                {
                    "p_actor_slug": actor_slug,
                    "p_query_embedding": embedding,
                    "p_days_back": int(days_back),
                    "p_limit": 1,
                },
            ).execute()
        except Exception:
            return None
        data = resp.data or []
        return data[0] if data else None

    def insert_signals(self, signals: list[SignalRow]) -> int:
        if not signals:
            return 0
        payload = []
        for s in signals:
            row = {
                "run_id": s.run_id,
                "actor_slug": s.actor_slug,
                "system": "hermes",
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
            }
            if s.embedding is not None:
                row["embedding"] = s.embedding
            payload.append(row)
        resp = (
            self._client.table("signals")
            .upsert(payload, on_conflict="actor_slug,source_url,content_hash", ignore_duplicates=True)
            .execute()
        )
        return len(resp.data or [])

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
