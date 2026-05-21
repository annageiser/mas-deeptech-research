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

    @staticmethod
    def derive_signal_rows(run_id: str, raw_signals: list[dict[str, Any]]) -> list[SignalRow]:
        rows: list[SignalRow] = []
        for s in raw_signals:
            evidence = s.get("evidence_quote") or ""
            content_hash = hashlib.sha256(
                f"{s.get('actor_slug')}|{s.get('source_url')}|{evidence}".encode("utf-8")
            ).hexdigest()
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
                )
            )
        return rows

    def insert_signals(self, signals: list[SignalRow]) -> int:
        if not signals:
            return 0
        payload = [
            {
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
            for s in signals
        ]
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
