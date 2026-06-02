"""arXiv collector — uses the public Atom export, no auth required.

We deliberately use the documented `https://export.arxiv.org/api/query`
endpoint (returns Atom XML). Each entry becomes one Document for the
Extractor.

Throttling: arXiv's terms of use ask for at most 1 request every 3 seconds.
The per-actor Loop in System A hits this collector once per actor in fast
succession, so we keep a module-level "last call" timestamp and sleep just
enough between requests to stay under the limit.

Author-affiliation check (v0.4.1): a recurring bug in v0.4.0 was that a
paper *mentioning* an actor (in references, acknowledgments, or
compared-against-work) would land as a publication signal attributed to
that actor. arXiv's Atom feed exposes per-author `<arxiv:affiliation>`
tags; we now match the actor's `name` + `aliases` against those strings
and drop papers where no author's affiliation matches.

Soft-fail policy: when the paper carries NO affiliation tags at all (a
small fraction of older submissions), we fall back to matching the actor
name in the title or abstract. A paper with no affiliation data AND no
in-body mention is dropped — keeps the precision-over-recall posture
that the rest of the v0.4.0 pipeline takes.
"""

from __future__ import annotations

import hashlib
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode

import feedparser
import httpx

from ..schema import Actor, Document


# Namespaces in the arXiv Atom feed. feedparser drops the namespaced
# `<arxiv:affiliation>` child of `<author>` (it sanitises authors to
# a fixed {name, href, email} schema), so we parse affiliations via
# ElementTree separately and pair them back up by entry id.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"


_ARXIV_MIN_INTERVAL = 3.1  # seconds — arXiv asks for ≥3s between requests
_last_call_at = 0.0
_throttle_lock = threading.Lock()


def _throttle() -> None:
    """Sleep just enough since the previous arXiv request."""
    global _last_call_at
    with _throttle_lock:
        elapsed = time.monotonic() - _last_call_at
        if elapsed < _ARXIV_MIN_INTERVAL:
            time.sleep(_ARXIV_MIN_INTERVAL - elapsed)
        _last_call_at = time.monotonic()


ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"

# arXiv field prefixes — if the caller-provided query already starts with one
# of these, we use it verbatim (no `all:` wrap). Otherwise we wrap as `all:`
# so a bare actor name still searches across all metadata.
# Ref: https://info.arxiv.org/help/api/user-manual.html#query_details
_ARXIV_FIELD_PREFIXES = ("ti:", "au:", "abs:", "co:", "jr:", "cat:", "rn:", "id:", "all:", "aff:")


def _normalise_arxiv_query(raw: str) -> str:
    """Pass through `aff:` / `au:` etc. unchanged; wrap bare text as `all:`.

    Several actor records use `aff:"ETH Zurich" AND (qubit OR quantum)` to
    bias toward affiliation matches. Wrapping that in `all:` would break the
    field operator; the older collector did exactly that, which silently
    weakened affiliation filtering for ~half the actors.
    """
    s = raw.strip()
    if not s:
        return ""
    lo = s.lower()
    if any(lo.startswith(p) for p in _ARXIV_FIELD_PREFIXES):
        return s
    return f"all:{s}"


def _parse_affiliations_by_id(xml_text: str) -> dict[str, list[str]]:
    """Build `{entry_id: [affiliation, ...]}` by parsing the raw Atom XML.

    feedparser silently drops the namespaced `<arxiv:affiliation>` child
    elements when it normalises authors, so we side-load this with
    ElementTree and pair back up by entry `<id>` later."""
    out: dict[str, list[str]] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for entry in root.findall(f"{_ATOM_NS}entry"):
        eid = (entry.findtext(f"{_ATOM_NS}id") or "").strip()
        if not eid:
            continue
        affs: list[str] = []
        for author in entry.findall(f"{_ATOM_NS}author"):
            for aff in author.findall(f"{_ARXIV_NS}affiliation"):
                txt = (aff.text or "").strip()
                if txt:
                    affs.append(txt)
        out[eid] = affs
    return out


def _actor_needles(actor: Actor) -> list[str]:
    """Lowercase, stripped match strings for the actor: name + aliases."""
    out: list[str] = []
    for n in [actor.name] + list(actor.aliases or []):
        n = (n or "").strip().lower()
        if n:
            out.append(n)
    return out


def _matches_actor(needles: list[str], haystack: str) -> bool:
    """Case-insensitive substring match. We deliberately don't use word
    boundaries: 'EPFL' should also match 'EPFL-LQM' as an affiliation."""
    if not haystack or not needles:
        return False
    lower = haystack.lower()
    return any(n in lower for n in needles)


def _belongs_to_actor(
    *, affiliations: list[str], title: str, summary: str, actor: Actor
) -> tuple[bool, str]:
    """Return (keep, reason). Drop papers the actor didn't author.

    Order:
      1. If ANY author affiliation matches the actor → keep (affiliation-
         attested authorship is the strongest signal).
      2. If the paper has NO affiliation tags at all (some older papers,
         and the .OAI feed variant), fall back to checking the title /
         abstract for the actor's name. A bare mention is weaker but
         plausible.
      3. Otherwise → drop (mentioned in body but not in any author's
         affiliation = third-party mention, not authorship).
    """
    needles = _actor_needles(actor)
    if not needles:
        return True, "no actor needles — cannot verify; let through"

    if affiliations:
        for a in affiliations:
            if _matches_actor(needles, a):
                return True, f"author affiliation: {a}"
        return False, "no author affiliation matches the actor"

    if _matches_actor(needles, f"{title}\n{summary}"):
        return True, "no affiliation tags; actor name appears in title/abstract"
    return False, "no affiliation tags and no actor mention in title/abstract"


def collect_arxiv(
    actor: Actor,
    *,
    max_results: int = 5,
    timeout: float = 30.0,
    enforce_authorship: bool = True,
) -> list[Document]:
    """Return up to `max_results` recent arXiv entries for an actor.

    `actor.arxiv_query` is used directly when it starts with an arXiv field
    operator (`aff:`, `au:`, `ti:`, etc.); otherwise it's wrapped as
    `all:<query>`. Falls back to the actor's name if `arxiv_query` is empty.

    When `enforce_authorship=True` (default), each returned entry is
    cross-checked against the actor's `name` + `aliases` via the
    `arxiv:affiliation` tags in the Atom feed. Papers that merely
    *mention* the actor in references or acknowledgments are dropped.
    Pass `enforce_authorship=False` to keep the v0.3.0 behaviour (for
    backwards-compat or a wider-but-noisier scrape).
    """
    query = _normalise_arxiv_query(actor.arxiv_query or actor.name)
    if not query:
        return []

    # Request more than max_results so the authorship filter can drop
    # noise without reducing the final yield. 3x is empirically about
    # right — arXiv's relevance ranking puts authored papers near the
    # top of a name-query, so the first ~2x usually contains all the
    # genuine hits. Capped at 30 to stay polite.
    requested = min(30, max(max_results, max_results * 3 if enforce_authorship else max_results))
    params = urlencode(
        {
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(requested),
        }
    )
    url = f"{ARXIV_ENDPOINT}?{params}"

    # arXiv now serves https; the http endpoint returns 301. Follow redirects
    # so we don't lose every actor's papers to the http→https hop.
    _throttle()
    with httpx.Client(
        timeout=timeout,
        headers={"User-Agent": "masfactory-thesis/0.1 (research)"},
        follow_redirects=True,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    # Side-load affiliations from the raw XML (feedparser drops them).
    aff_by_id = _parse_affiliations_by_id(resp.text) if enforce_authorship else {}

    documents: list[Document] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or "").strip()
        link = entry.get("link") or ""
        if not title or not summary:
            continue

        # Author-affiliation gate (v0.4.1) — the headline fix for the
        # "paper attributed to actor who didn't write it" bug.
        if enforce_authorship:
            eid = (entry.get("id") or "").strip()
            affs = aff_by_id.get(eid, [])
            keep, _reason = _belongs_to_actor(
                affiliations=affs, title=title, summary=summary, actor=actor
            )
            if not keep:
                continue

        body = f"{title}\n\n{summary}"
        documents.append(
            Document(
                source_kind="arxiv",
                source_url=link,
                actor_slug=actor.slug,
                title=title,
                text=body,
                fetched_at=datetime.now(timezone.utc),
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            )
        )
        if len(documents) >= max_results:
            break
    return documents
