"""CRUD for the editorial training layer (v0.4.37).

Two tables, both managed through the dashboard:

  - public.manual_signals   — hand-curated signals (URL + labels +
                              notes + related actors). Consumed by both
                              producer systems as few-shot examples
                              and propagated into public.signals as
                              system='manual' for dashboard visibility.

  - public.signal_sources   — RSS / Atom / URL sources managed via CRUD
                              instead of data/raw/rss_feeds.yaml. Both
                              systems' collectors read enabled sources
                              and skip those whose last_fetched_at is
                              newer than crawl_frequency_hours.

Validation policy:
  - URLs: stripped + lowercased for the unique key (DB layer enforces).
  - Labels: free-form text array, lower-cased on write so filtering by
    label is case-insensitive.
  - Actor slugs: validated against public.actors at write time so
    typos surface immediately rather than silently broadening the
    set during prompt assembly.

Auth: every endpoint here MUTATES. The dashboard sits behind Caddy
basic-auth so this is "Anna only" by deployment. If you ever route
these endpoints through a public path, add an explicit admin check
in main.py before this module gets called.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator

from . import data_access as da


# Ehrenthal four-signal scheme — same canonical set the persisters
# enforce. Manual signals may optionally set signal_type explicitly;
# anything outside the four is rejected at the API layer.
VALID_SIGNAL_TYPES = {
    "legitimacy",
    "customer_cocreation",
    "community_ecosystem",
    "future_trajectory",
}

VALID_SOURCE_KINDS = {"rss", "atom", "url"}

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _norm_url(url: str) -> str:
    return (url or "").strip()


def _norm_labels(labels: list[str] | None) -> list[str]:
    if not labels:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in labels:
        v = (raw or "").strip().lower()
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _norm_actor_slugs(slugs: list[str] | None) -> list[str]:
    if not slugs:
        return []
    valid = set(da.actors()["slug"].tolist()) if not da.actors().empty else set()
    seen: set[str] = set()
    out: list[str] = []
    for s in slugs:
        v = (s or "").strip().lower()
        if not v or v in seen:
            continue
        if valid and v not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"unknown actor_slug: {v!r} (not in public.actors)",
            )
        seen.add(v)
        out.append(v)
    return out


# ---------- manual signals ----------


class ManualSignalIn(BaseModel):
    source_url: str = Field(min_length=8, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=4000)
    labels: list[str] = Field(default_factory=list)
    signal_type: Optional[str] = None
    dimension: Optional[str] = Field(default=None, max_length=120)
    actor_slugs: list[str] = Field(default_factory=list)

    @field_validator("source_url")
    @classmethod
    def _v_url(cls, v: str) -> str:
        v = _norm_url(v)
        if not _URL_RE.match(v):
            raise ValueError("source_url must start with http:// or https://")
        return v

    @field_validator("signal_type")
    @classmethod
    def _v_signal_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        if v not in VALID_SIGNAL_TYPES:
            raise ValueError(
                f"signal_type must be one of {sorted(VALID_SIGNAL_TYPES)} "
                f"or null; got {v!r}"
            )
        return v


class ManualSignalPatch(BaseModel):
    # All optional — only included fields get updated.
    source_url: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    labels: Optional[list[str]] = None
    signal_type: Optional[str] = None
    dimension: Optional[str] = None
    actor_slugs: Optional[list[str]] = None

    @field_validator("source_url")
    @classmethod
    def _v_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = _norm_url(v)
        if not _URL_RE.match(v):
            raise ValueError("source_url must start with http:// or https://")
        return v

    @field_validator("signal_type")
    @classmethod
    def _v_signal_type(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if v not in VALID_SIGNAL_TYPES:
            raise ValueError(
                f"signal_type must be one of {sorted(VALID_SIGNAL_TYPES)} "
                f"or null; got {v!r}"
            )
        return v


def list_manual_signals(*, limit: int = 500) -> list[dict[str, Any]]:
    client = da.client()
    resp = (
        client.table("manual_signals")
        .select("*")
        .order("updated_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data or []


def get_manual_signal(signal_id: str) -> Optional[dict[str, Any]]:
    client = da.client()
    resp = (
        client.table("manual_signals")
        .select("*")
        .eq("id", signal_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def create_manual_signal(payload: ManualSignalIn) -> dict[str, Any]:
    client = da.client()
    row = {
        "source_url": payload.source_url,
        "title": payload.title or None,
        "notes": payload.notes or None,
        "labels": _norm_labels(payload.labels),
        "signal_type": payload.signal_type,
        "dimension": (payload.dimension or "").strip() or None,
        "actor_slugs": _norm_actor_slugs(payload.actor_slugs),
    }
    try:
        resp = client.table("manual_signals").insert(row).execute()
    except Exception as exc:
        msg = str(exc)
        if "duplicate key" in msg or "unique" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"manual_signals.source_url already exists: {payload.source_url!r}",
            )
        raise HTTPException(status_code=500, detail=f"insert failed: {exc}")
    return (resp.data or [{}])[0]


def patch_manual_signal(signal_id: str, payload: ManualSignalPatch) -> dict[str, Any]:
    existing = get_manual_signal(signal_id)
    if not existing:
        raise HTTPException(status_code=404, detail="manual_signal not found")

    update: dict[str, Any] = {}
    data = payload.model_dump(exclude_unset=True)
    if "source_url" in data:
        update["source_url"] = data["source_url"]
    if "title" in data:
        update["title"] = (data["title"] or "").strip() or None
    if "notes" in data:
        update["notes"] = (data["notes"] or "").strip() or None
    if "labels" in data:
        update["labels"] = _norm_labels(data["labels"])
    if "signal_type" in data:
        update["signal_type"] = data["signal_type"]
    if "dimension" in data:
        update["dimension"] = (data["dimension"] or "").strip() or None
    if "actor_slugs" in data:
        update["actor_slugs"] = _norm_actor_slugs(data["actor_slugs"])

    if not update:
        return existing  # nothing to do

    client = da.client()
    try:
        resp = (
            client.table("manual_signals")
            .update(update)
            .eq("id", signal_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"update failed: {exc}")
    rows = resp.data or []
    return rows[0] if rows else {**existing, **update}


def delete_manual_signal(signal_id: str) -> None:
    existing = get_manual_signal(signal_id)
    if not existing:
        raise HTTPException(status_code=404, detail="manual_signal not found")
    client = da.client()
    try:
        client.table("manual_signals").delete().eq("id", signal_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"delete failed: {exc}")


# ---------- signal sources ----------


class SignalSourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    kind: str = Field(description="rss | atom | url")
    label: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)
    labels: list[str] = Field(default_factory=list)
    actor_slugs: list[str] = Field(default_factory=list)
    enabled: bool = True
    crawl_frequency_hours: int = Field(default=24, ge=0, le=720)

    @field_validator("url")
    @classmethod
    def _v_url(cls, v: str) -> str:
        v = _norm_url(v)
        if not _URL_RE.match(v):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("kind")
    @classmethod
    def _v_kind(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in VALID_SOURCE_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(VALID_SOURCE_KINDS)}; got {v!r}"
            )
        return v


class SignalSourcePatch(BaseModel):
    url: Optional[str] = None
    kind: Optional[str] = None
    label: Optional[str] = None
    notes: Optional[str] = None
    labels: Optional[list[str]] = None
    actor_slugs: Optional[list[str]] = None
    enabled: Optional[bool] = None
    crawl_frequency_hours: Optional[int] = Field(default=None, ge=0, le=720)

    @field_validator("url")
    @classmethod
    def _v_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = _norm_url(v)
        if not _URL_RE.match(v):
            raise ValueError("url must start with http:// or https://")
        return v

    @field_validator("kind")
    @classmethod
    def _v_kind(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        v = v.strip().lower()
        if v not in VALID_SOURCE_KINDS:
            raise ValueError(
                f"kind must be one of {sorted(VALID_SOURCE_KINDS)}; got {v!r}"
            )
        return v


def list_sources(*, enabled: Optional[bool] = None, limit: int = 500) -> list[dict[str, Any]]:
    client = da.client()
    q = client.table("signal_sources").select("*")
    if enabled is not None:
        q = q.eq("enabled", enabled)
    resp = q.order("updated_at", desc=True).limit(limit).execute()
    return resp.data or []


def get_source(source_id: str) -> Optional[dict[str, Any]]:
    client = da.client()
    resp = (
        client.table("signal_sources")
        .select("*")
        .eq("id", source_id)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def create_source(payload: SignalSourceIn) -> dict[str, Any]:
    client = da.client()
    row = {
        "url": payload.url,
        "kind": payload.kind,
        "label": (payload.label or "").strip() or None,
        "notes": (payload.notes or "").strip() or None,
        "labels": _norm_labels(payload.labels),
        "actor_slugs": _norm_actor_slugs(payload.actor_slugs),
        "enabled": bool(payload.enabled),
        "crawl_frequency_hours": int(payload.crawl_frequency_hours),
    }
    try:
        resp = client.table("signal_sources").insert(row).execute()
    except Exception as exc:
        msg = str(exc)
        if "duplicate key" in msg or "unique" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"signal_sources.url already exists: {payload.url!r}",
            )
        raise HTTPException(status_code=500, detail=f"insert failed: {exc}")
    return (resp.data or [{}])[0]


def patch_source(source_id: str, payload: SignalSourcePatch) -> dict[str, Any]:
    existing = get_source(source_id)
    if not existing:
        raise HTTPException(status_code=404, detail="signal_source not found")

    update: dict[str, Any] = {}
    data = payload.model_dump(exclude_unset=True)
    if "url" in data:
        update["url"] = data["url"]
    if "kind" in data:
        update["kind"] = data["kind"]
    if "label" in data:
        update["label"] = (data["label"] or "").strip() or None
    if "notes" in data:
        update["notes"] = (data["notes"] or "").strip() or None
    if "labels" in data:
        update["labels"] = _norm_labels(data["labels"])
    if "actor_slugs" in data:
        update["actor_slugs"] = _norm_actor_slugs(data["actor_slugs"])
    if "enabled" in data:
        update["enabled"] = bool(data["enabled"])
    if "crawl_frequency_hours" in data:
        update["crawl_frequency_hours"] = int(data["crawl_frequency_hours"])

    if not update:
        return existing

    client = da.client()
    try:
        resp = (
            client.table("signal_sources")
            .update(update)
            .eq("id", source_id)
            .execute()
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"update failed: {exc}")
    rows = resp.data or []
    return rows[0] if rows else {**existing, **update}


def delete_source(source_id: str) -> None:
    existing = get_source(source_id)
    if not existing:
        raise HTTPException(status_code=404, detail="signal_source not found")
    client = da.client()
    try:
        client.table("signal_sources").delete().eq("id", source_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"delete failed: {exc}")


def mark_source_fetched(
    source_id: str,
    *,
    status: str,
    item_count: int = 0,
    error: Optional[str] = None,
) -> None:
    """Producer-side helper. Update a source's last-fetched bookkeeping.

    Called from systems/masfactory and systems/hermes collectors after
    each fetch. Not exposed as an HTTP endpoint — producer containers
    use the Supabase service-role key directly. Kept here so the
    update shape lives next to its schema.
    """
    client = da.client()
    client.table("signal_sources").update(
        {
            "last_fetched_at": datetime.now(timezone.utc).isoformat(),
            "last_status": status,
            "last_error": (error or "")[:2000] or None,
            "last_item_count": int(item_count),
        }
    ).eq("id", source_id).execute()
