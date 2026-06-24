"""Retriever — pure-Python CustomNode that calls the collectors.

Not an Agent because there's no judgement to make: given a plan, fetch the
documents. We keep the network IO out of the LLM loop so token cost is
predictable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from masfactory import CustomNode, NodeTemplate

from ..collection import (
    collect_arxiv,
    collect_google_news,
    collect_patents,
    collect_press_releases,
    collect_rss_for_actors,
    collect_website,
)
from ..schema import Actor, Document
from ..training_layer import load_training_layer, mark_source_fetched


def _retrieve(_input: dict, attrs: dict) -> dict:
    raw_plan = attrs.get("plan_json", "") or "{}"
    if isinstance(raw_plan, str):
        # The Planner emits a JSON string; tolerate already-parsed dicts too.
        try:
            plan = json.loads(_strip_fences(raw_plan))
        except json.JSONDecodeError:
            plan = {}
    else:
        plan = raw_plan or {}

    actors_by_slug: dict[str, dict] = {a["slug"]: a for a in attrs.get("actor_pool", [])}

    # v0.4.0 — wider collection funnel. Raised across the board so the Critic
    # (now substantially stricter) has more candidates to filter and the
    # final corpus reflects a richer evidence base. Cron knobs in .env.example
    # let operators tune per-collector limits independently.
    limit_arxiv = int(attrs.get("limit_arxiv_per_actor", 10) or 10)
    limit_web = int(attrs.get("limit_website_pages_per_actor", 5) or 5)
    limit_news = int(attrs.get("limit_news_per_actor", 10) or 10)
    limit_press = int(attrs.get("limit_press_per_actor", 10) or 10)
    limit_patents = int(attrs.get("limit_patents_per_actor", 10) or 10)
    cache_dir = attrs.get("web_cache_dir", "/data/raw/web_cache") or "/data/raw/web_cache"

    documents: list[dict] = []
    errors: list[dict] = list(attrs.get("retriever_errors", []) or [])

    # v0.4.37 — editorial training layer. Read once per run; expose to
    # downstream nodes via attrs so the Classifier prompt builder can
    # also pull few-shot examples without re-fetching. Best-effort:
    # load_training_layer returns an empty layer on any error.
    training = load_training_layer()
    training_meta = {
        "manual_signals_total": len(training.manual),
        "sources_enabled_total": len(training.sources),
        "per_actor": {},
    }

    # v0.4.2 — RSS feed-discovery layer. Runs ONCE per actor pool (not per
    # actor) because RSS feeds are feed-first, not actor-first: one fetch
    # broadcasts entries to every matching actor. Saves N×fan-out HTTP calls.
    # Result merged into the per-actor `documents` list below.
    rss_by_actor: dict[str, list[dict]] = {}
    try:
        actor_objs: list[Actor] = []
        for entry in plan.get("selected", []):
            slug = entry.get("slug")
            actor_dict = actors_by_slug.get(slug) if slug else None
            if actor_dict:
                actor_objs.append(Actor.model_validate(actor_dict))
        if actor_objs:
            raw_map = collect_rss_for_actors(actor_objs, max_entries_per_feed=25)
            rss_by_actor = {
                k: [d.model_dump(mode="json") for d in v] for k, v in raw_map.items()
            }
    except Exception as exc:
        errors.append({"slug": "*", "source": "rss", "error": str(exc)})

    for entry in plan.get("selected", []):
        slug = entry.get("slug")
        sources = entry.get("sources", []) or []
        actor_dict = actors_by_slug.get(slug)
        if not actor_dict:
            continue
        actor = Actor.model_validate(actor_dict)

        if "arxiv" in sources:
            try:
                documents.extend(d.model_dump(mode="json") for d in collect_arxiv(actor, max_results=limit_arxiv))
            except Exception as exc:  # collectors should not break the graph
                errors.append({"slug": slug, "source": "arxiv", "error": str(exc)})

        if "website" in sources:
            try:
                documents.extend(
                    d.model_dump(mode="json")
                    for d in collect_website(actor, max_pages=limit_web, cache_dir=cache_dir)
                )
            except Exception as exc:
                errors.append({"slug": slug, "source": "website", "error": str(exc)})

        # Google News is broader-web third-party coverage. Always opt in unless
        # the plan explicitly says no — gives non-actor-controlled signal.
        if "news" in sources or not sources or ("arxiv" in sources or "website" in sources):
            try:
                documents.extend(
                    d.model_dump(mode="json")
                    for d in collect_google_news(actor, max_results=limit_news)
                )
            except Exception as exc:
                errors.append({"slug": slug, "source": "news", "error": str(exc)})

        # Press-release aggregator (Bing News with PR-flavoured query). Distinct
        # ranker + aggregator coverage from Google News; together the two read
        # the "press" signal channel more completely (Kolbe & Burnett 1991
        # content-analysis triangulation). Always opt in for the same reason.
        if "press" in sources or not sources or ("arxiv" in sources or "website" in sources or "news" in sources):
            try:
                documents.extend(
                    d.model_dump(mode="json")
                    for d in collect_press_releases(actor, max_results=limit_press)
                )
            except Exception as exc:
                errors.append({"slug": slug, "source": "press", "error": str(exc)})

        # RSS feed-discovery — pre-computed once for the whole actor pool
        # above. Just merge the per-actor slice.
        if rss_by_actor.get(slug):
            documents.extend(rss_by_actor[slug])

        # EPO OPS patent search → fills source_kind='swissreg'. Returns []
        # silently if EPO_OPS_CONSUMER_KEY/SECRET aren't configured, so this
        # is harmless to enable by default. Patent filings are the strongest
        # costly-signal channel (Spence 1973 / Ehrenthal 2026) — high schema
        # weight when present.
        if "patents" in sources or "swissreg" in sources or not sources or (
            "arxiv" in sources or "website" in sources or "news" in sources
        ):
            try:
                documents.extend(
                    d.model_dump(mode="json")
                    for d in collect_patents(actor, max_results=limit_patents)
                )
            except Exception as exc:
                errors.append({"slug": slug, "source": "patents", "error": str(exc)})

        # v0.4.37 — editorial training layer per-actor injection.
        #   1. Recommended URLs from manual signals (curated by Anna via
        #      /labels) → treated as additional "manual" documents so the
        #      Extractor / Classifier process them through the normal pipe.
        #   2. URLs from due signal_sources (CRUD via /sources) → same
        #      treatment. crawl_frequency_hours acts as a floor: the
        #      training layer filters to sources whose last_fetched_at is
        #      older than (now - crawl_frequency_hours).
        # We mark each fetched source via mark_source_fetched so the
        # crawl-frequency hint actually advances. Manual signals stay in
        # the manual_signals table; their propagation into public.signals
        # as system='manual' happens separately via
        # systems/masfactory/masfactory_system/scripts/sync_manual_signals.py
        # (chained from cron) rather than this Retriever.
        actor_training_urls: list[str] = []
        _now = datetime.now(timezone.utc)
        for url in training.recommended_urls_for_actor(slug):
            actor_training_urls.append(url)
            documents.append(
                Document(
                    actor_slug=slug,
                    source_kind="manual",
                    source_url=url,
                    title=f"Manual recommendation for {slug}",
                    text="(URL contributed by /labels — body fetched downstream)",
                    fetched_at=_now,
                    content_hash=hashlib.sha256(
                        f"manual|{slug}|{url}".encode("utf-8")
                    ).hexdigest(),
                ).model_dump(mode="json")
            )

        for src in training.sources_due(actor_slug=slug):
            actor_training_urls.append(src.url)
            documents.append(
                Document(
                    actor_slug=slug,
                    source_kind="website" if src.kind == "url" else "news",
                    source_url=src.url,
                    title=src.label or src.url,
                    text="(URL contributed by /sources — body fetched downstream)",
                    fetched_at=_now,
                    content_hash=hashlib.sha256(
                        f"source|{slug}|{src.url}".encode("utf-8")
                    ).hexdigest(),
                ).model_dump(mode="json")
            )
            try:
                mark_source_fetched(src.id, status="ok", item_count=1)
            except Exception:
                pass  # best-effort bookkeeping

        if actor_training_urls:
            training_meta["per_actor"][slug] = actor_training_urls

    # Group documents by actor_slug so the per-actor Loop downstream can
    # process one actor at a time (smaller Extractor prompts → cleaner
    # attribution + lower context-window risk). Order preserved by plan.
    grouped: list[dict] = []
    seen: set[str] = set()
    for entry in plan.get("selected", []):
        slug = entry.get("slug")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        actor_docs = [d for d in documents if d.get("actor_slug") == slug]
        if actor_docs:  # skip actors with zero docs (Loop has nothing to process)
            grouped.append({"actor_slug": slug, "documents": actor_docs})

    return {
        "documents": documents,
        "documents_count": len(documents),
        "documents_json": json.dumps(documents),
        "documents_by_actor": grouped,
        "documents_by_actor_count": len(grouped),
        "actor_loop_index": 0,
        "all_classified": [],
        "all_critique": [],
        "all_surviving_signals": [],
        "retriever_errors": errors,
        # v0.4.37 — surfaces the editorial layer to downstream nodes
        # (and to the audit folder via Persistence). Classifier prompt
        # builders can read training_few_shot from here when wiring
        # few-shot examples into their prompts (follow-up).
        "training_meta": training_meta,
        "training_few_shot": [
            {
                "actor_slug": slug,
                "examples": [
                    {
                        "source_url": ex.source_url,
                        "title": ex.title,
                        "notes": ex.notes,
                        "labels": ex.labels,
                        "signal_type": ex.signal_type,
                        "dimension": ex.dimension,
                    }
                    for ex in training.few_shot_for_actor(slug, max_examples=4)
                ],
            }
            for slug in {e.get("slug") for e in plan.get("selected", []) if e.get("slug")}
        ],
    }


def _strip_fences(raw: str) -> str:
    """Defensively strip ```json fences and the closing tag the formatter adds."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    # The Tagged formatter may wrap the JSON in <plan_json>...</plan_json>.
    if "</plan_json>" in text:
        text = text.split("</plan_json>")[0]
    if "<plan_json>" in text:
        text = text.split("<plan_json>")[1]
    return text.strip()


RetrieverNode = NodeTemplate(CustomNode, forward=_retrieve, pull_keys=None, push_keys=None)
