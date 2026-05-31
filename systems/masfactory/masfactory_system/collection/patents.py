"""Patent collector — fills the schema's reserved `source_kind='swissreg'`.

## Why patents matter for the thesis signal model

In Spence's (1973) signalling framework — operationalised in our schema
v0.3.0 via Ehrenthal et al. (2026) — patent filings are a textbook
**costly signal**: filing fees, attorney fees, public disclosure of
technical detail, and a multi-year prosecution timeline mean only actors
with genuine R&D output bother filing. Patents therefore carry the
strongest credibility weight (`signal_cost='high'`) in our schema, on par
with regulatory and infrastructure signals. Picking them up is the
remaining gap in our broader-web coverage (along with arXiv + Google
News + press-release aggregator).

## Why EPO OPS rather than swissreg.ch

The original disposition names "swissreg" because that's the public face of
the Swiss IP Office (https://www.swissreg.ch). The same data is available
via the **European Patent Office's Open Patent Services (OPS) API** with a
*much* more stable contract:

  - Documented REST + JSON (swissreg.ch's only public interface is a JS-
    rendered HTML form).
  - Free tier (4 GB/week) — well under our footprint.
  - Covers Swiss national filings (CH*), PCT (WO*), and European (EP*)
    patents — strictly broader than swissreg.ch.
  - Stable for years (versioned API; current is 3.2).

We keep the schema's `source_kind='swissreg'` name verbatim so the column
matches the disposition's vocabulary, even though the underlying API is
EPO OPS. The source_url points at Espacenet (the EPO's public patent
viewer) for any human follow-up — same patents, prettier UI.

## Auth gate

Env-gated by `EPO_OPS_CONSUMER_KEY` + `EPO_OPS_CONSUMER_SECRET`. If either
is missing, the collector returns []. No keys → no regression, no
side effects. Registration takes ~5 minutes at https://developers.epo.org;
the keys then go in `.env` alongside the other secrets.

## Query strategy

For each actor, we run one OPS search:

    pa = "<Actor Name>"
    AND
    (
        ic = G06N10/* OR ic = H04L9/0852/* OR
        ti = quantum  OR ab = quantum
    )

  - `pa` matches the applicant (the organisation, not the inventor).
  - The OR-group restricts to quantum-relevant patents — G06N10 is the
    IPC class for quantum-computing methods, H04L9/0852 for quantum-key
    distribution; title/abstract keyword catches the rest (e.g. quantum
    sensors classified under G01R33).
  - We do *not* restrict by publication-country (CH*) because Swiss
    actors regularly file PCT/EP applications that don't carry a CH
    publication number but are nonetheless their patents.

Each result becomes a Document with source_kind='swissreg', source_url
pointing at Espacenet, title=patent title, text=title+abstract, and a
sha256 content_hash over (publication_number, title) so re-runs are
idempotent.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from ..schema import Actor, Document

log = logging.getLogger(__name__)


OPS_BASE = "https://ops.epo.org/3.2"
OPS_TOKEN_URL = f"{OPS_BASE}/auth/accesstoken"
OPS_SEARCH_URL = f"{OPS_BASE}/rest-services/published-data/search/biblio"
USER_AGENT = "masfactory-thesis/0.1 (+https://github.com/anna-geiser/mas-deeptech-research)"

# IPC classes most closely aligned with the thesis's quantum corpus. We OR
# title/abstract keyword search alongside these because not all quantum work
# is classified under a quantum-specific IPC code (e.g. quantum sensors are
# often under G01R, G01J, G01N depending on the modality).
QUANTUM_IPC = ("G06N10", "H04L9/0852")


# Module-level OAuth2 token cache. Tokens are valid 20 min by spec; we treat
# them as good for 18 min to leave a comfortable margin against clock skew.
_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def is_configured() -> bool:
    """True iff the env carries both halves of an EPO OPS consumer credential."""
    return bool(
        os.environ.get("EPO_OPS_CONSUMER_KEY", "").strip()
        and os.environ.get("EPO_OPS_CONSUMER_SECRET", "").strip()
    )


def _get_token(client: httpx.Client) -> Optional[str]:
    """OAuth2 client-credentials → access token. Cached at module level."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 30:
        return _token_cache["access_token"]

    key = os.environ.get("EPO_OPS_CONSUMER_KEY", "").strip()
    secret = os.environ.get("EPO_OPS_CONSUMER_SECRET", "").strip()
    if not key or not secret:
        return None

    basic = b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    try:
        resp = client.post(
            OPS_TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            content="grant_type=client_credentials",
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        log.warning("EPO OPS token request failed: %s", exc)
        return None

    token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 0) or 0)
    if not token:
        return None
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + max(60, expires_in - 120)  # 2-min safety margin
    return token


def _build_cql(actor: Actor) -> str:
    """Compose the CQL search query.

    Quoted applicant name → exact-phrase match. The OR-group narrows to
    quantum-relevant patents via IPC OR title/abstract keyword. We
    deliberately do NOT add `pn=CH*` — Swiss actors routinely file PCT/EP
    applications that don't carry a CH publication number but are still
    their patents.
    """
    name = actor.name.replace('"', "").strip()
    ipc_clauses = " OR ".join(f'ic="{cls}"' for cls in QUANTUM_IPC)
    return f'pa="{name}" AND ({ipc_clauses} OR ti=quantum OR ab=quantum)'


def _extract_documents(
    payload: dict, actor: Actor, *, now: datetime, max_results: int
) -> list[Document]:
    """Pull (publication_number, title, abstract, kind, country) out of an OPS
    search-biblio JSON response and shape Documents.

    The OPS JSON schema is verbose and inconsistent — exchange-documents can
    be a list or a single object, abstract may be absent, etc. We code
    defensively and skip any entry we can't make sense of.
    """
    docs: list[Document] = []

    def _as_list(x):
        if x is None:
            return []
        return x if isinstance(x, list) else [x]

    biblio_root = (
        payload.get("ops:world-patent-data", {})
        .get("ops:biblio-search", {})
        .get("ops:search-result", {})
        .get("exchange-documents", {})
    )

    for ex_doc_wrap in _as_list(biblio_root.get("exchange-document")):
        # exchange-document can itself be wrapped one more level deep when
        # multiple language variants are returned for the same publication.
        for ex_doc in _as_list(ex_doc_wrap):
            if not isinstance(ex_doc, dict):
                continue

            # ---- publication number ----
            country = ex_doc.get("@country", "")
            doc_num = ex_doc.get("@doc-number", "")
            kind = ex_doc.get("@kind", "")
            if not country or not doc_num:
                continue
            publication_number = f"{country}{doc_num}{kind}"

            # ---- title (prefer English, fall back to whatever's there) ----
            title = ""
            biblio = ex_doc.get("bibliographic-data", {})
            for t in _as_list(biblio.get("invention-title")):
                if not isinstance(t, dict):
                    continue
                lang = t.get("@lang", "")
                text = (t.get("$") or "").strip()
                if not text:
                    continue
                if lang == "en":
                    title = text
                    break
                if not title:
                    title = text
            if not title:
                title = f"Patent {publication_number}"

            # ---- abstract (English preferred) ----
            abstract = ""
            for ab in _as_list(ex_doc.get("abstract")):
                if not isinstance(ab, dict):
                    continue
                lang = ab.get("@lang", "")
                text_blob = ab.get("p")
                if isinstance(text_blob, dict):
                    text = (text_blob.get("$") or "").strip()
                elif isinstance(text_blob, list):
                    text = " ".join(
                        (p.get("$") or "").strip() if isinstance(p, dict) else str(p)
                        for p in text_blob
                    ).strip()
                elif isinstance(text_blob, str):
                    text = text_blob.strip()
                else:
                    continue
                if not text:
                    continue
                if lang == "en":
                    abstract = text
                    break
                if not abstract:
                    abstract = text

            # ---- compose Document ----
            source_url = (
                "https://worldwide.espacenet.com/patent/search/publication/"
                f"{country}/{doc_num}"
            )
            body = (title + "\n\n" + abstract).strip()
            docs.append(
                Document(
                    source_kind="swissreg",
                    source_url=source_url,
                    actor_slug=actor.slug,
                    title=title[:500],
                    text=body[:8_000],
                    fetched_at=now,
                    content_hash=hashlib.sha256(
                        f"{publication_number}|{title}".encode("utf-8")
                    ).hexdigest(),
                )
            )
            if len(docs) >= max_results:
                return docs

    return docs


def collect_patents(
    actor: Actor,
    *,
    max_results: int = 5,
    timeout: float = 25.0,
) -> list[Document]:
    """Search EPO OPS for quantum-relevant patents naming `actor` as applicant.

    Returns up to `max_results` Documents. Returns [] (no exception) on any
    of: missing credentials, OAuth failure, network failure, parse failure,
    or empty result set — the cron must never break on a collector hiccup.
    """
    if not is_configured():
        return []

    try:
        with httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            token = _get_token(client)
            if not token:
                return []

            cql = _build_cql(actor)
            params = {"q": cql, "Range": f"1-{max(1, min(20, int(max_results)))}"}
            resp = client.get(
                OPS_SEARCH_URL,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if resp.status_code == 404:
                # OPS returns 404 for "no hits" on some endpoints. Treat as empty.
                return []
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        log.warning("EPO OPS search failed for %s: %s", actor.slug, exc)
        return []

    now = datetime.now(timezone.utc)
    return _extract_documents(payload, actor, now=now, max_results=max_results)
