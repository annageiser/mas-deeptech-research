"""Retriever — pure-Python CustomNode that calls the collectors.

Not an Agent because there's no judgement to make: given a plan, fetch the
documents. We keep the network IO out of the LLM loop so token cost is
predictable.
"""

from __future__ import annotations

import json

from masfactory import CustomNode, NodeTemplate

from ..collection import collect_arxiv, collect_google_news, collect_website
from ..schema import Actor


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
    limit_arxiv = int(attrs.get("limit_arxiv_per_actor", 5) or 5)
    limit_web = int(attrs.get("limit_website_pages_per_actor", 2) or 2)
    limit_news = int(attrs.get("limit_news_per_actor", 5) or 5)
    cache_dir = attrs.get("web_cache_dir", "/data/raw/web_cache") or "/data/raw/web_cache"

    documents: list[dict] = []
    errors: list[dict] = list(attrs.get("retriever_errors", []) or [])

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
