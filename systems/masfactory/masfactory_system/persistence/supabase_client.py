"""Thin wrapper around supabase-py for the rows this system writes.

All writes are idempotent — the cron schedule means the same run can fire
twice (e.g. after a transient network blip on the host). `signals` carries a
unique constraint on (actor_slug, source_url, content_hash) so duplicate
inserts are silently ignored at the DB level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from supabase import Client, create_client

from ..config import Settings


@dataclass
class RunRow:
    id: str
    system: str = "masfactory"
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


class SupabaseStore:
    def __init__(self, settings: Settings):
        if not settings.has_supabase:
            raise RuntimeError("Supabase credentials missing — set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        self._client: Client = create_client(settings.supabase_url, settings.supabase_service_key)

    # ---------- actors ----------

    def upsert_actors(self, actors: list[dict[str, Any]]) -> None:
        if not actors:
            return
        self._client.table("actors").upsert(actors, on_conflict="slug").execute()

    # ---------- runs ----------

    def start_run(self, *, actor_slugs: list[str], config_snapshot: dict[str, Any]) -> str:
        payload = {
            "system": "masfactory",
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
            .upsert(rows, on_conflict="actor_slug,source_url,content_hash", ignore_duplicates=True)
            .execute()
        )
        return len(resp.data or [])

    @staticmethod
    def _signal_to_row(s: SignalRow) -> dict[str, Any]:
        return {
            "run_id": s.run_id,
            "actor_slug": s.actor_slug,
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
