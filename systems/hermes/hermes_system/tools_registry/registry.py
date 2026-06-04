"""Tools Registry.

Each tool is a typed Python callable with a short docstring. The AIAgent
chooses one by name and supplies JSON arguments — we deliberately keep the
tool surface tiny so the comparison with System A's MASFactory CustomNodes is
apples-to-apples.

Tools currently exposed:
  - arxiv_search       (query, max_results)
  - website_fetch      (url, max_pages)
  - register_signal    (actor_slug, source_url, title, summary, evidence_quote, dimension, is_technical, confidence)
  - finish_actor       (summary_md)

Reuses the arXiv + website collectors from System A by import so both systems
hit the same external behaviour on the same sources.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolDef:
    name: str
    description: str
    func: Callable[..., Any]
    parameters: dict[str, str]   # arg name -> short type description (for the prompt only)

    def schema_for_prompt(self) -> str:
        params = ", ".join(f"{k}: {v}" for k, v in self.parameters.items()) if self.parameters else ""
        return f"- `{self.name}({params})` — {self.description}"


class ToolsRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def add(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def list(self) -> list[ToolDef]:
        return list(self._tools.values())

    def call(self, name: str, args: dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name].func(**args)

    def schema_block(self) -> str:
        return "\n".join(t.schema_for_prompt() for t in self.list())


# ---------- default tool implementations ----------


def register_default_tools(
    registry: ToolsRegistry,
    *,
    actor_slug: str,
    signal_buffer: list[dict[str, Any]],
    actor_name: str = "",
    actor_aliases: list[str] | None = None,
) -> None:
    """Install the four canonical tools the architecture diagram lists.

    `signal_buffer` is a shared list the `register_signal` tool appends to;
    the runner reads it after the loop finishes and ships rows to Supabase.

    `actor_name` + `actor_aliases` are used by the arxiv_search tool to
    enforce the author-affiliation check (v0.4.1 — fixes attribution of
    papers that merely mention the actor in references). Older callers that
    don't pass these arguments get the v0.3.0 lax behaviour for backward
    compatibility (the eval harness flags this with a warning).
    """
    from ..collectors import (
        collect_arxiv_for_query,
        collect_google_news_for_actor,
        collect_patents_for_actor,
        collect_press_releases_for_actor,
        collect_website_for_url,
    )

    _aliases = list(actor_aliases or [])

    def arxiv_search(query: str, max_results: int = 5) -> str:
        docs = collect_arxiv_for_query(
            query=query,
            max_results=max_results,
            actor_slug=actor_slug,
            actor_name=actor_name,
            aliases=_aliases,
        )
        return json.dumps(docs)

    def website_fetch(url: str, max_pages: int = 1) -> str:
        docs = collect_website_for_url(url=url, max_pages=max_pages, actor_slug=actor_slug)
        return json.dumps(docs)

    def news_search(actor_name: str, max_results: int = 5) -> str:
        """Google News RSS biased to Switzerland. Pass the actor's display
        name (not slug) — Google News matches better on real names."""
        docs = collect_google_news_for_actor(
            actor_name=actor_name, max_results=max_results, actor_slug=actor_slug
        )
        return json.dumps(docs)

    def press_search(actor_name: str, max_results: int = 5) -> str:
        """Press-release aggregator (Bing News with PR-flavoured query).
        Distinct ranker + aggregator coverage from `news_search` — call
        both for full content-analysis triangulation."""
        docs = collect_press_releases_for_actor(
            actor_name=actor_name, max_results=max_results, actor_slug=actor_slug
        )
        return json.dumps(docs)

    def patent_search(actor_name: str, max_results: int = 5) -> str:
        """EPO Open Patent Services search for quantum-relevant patents
        naming the actor as applicant. Returns [] if EPO_OPS_CONSUMER_KEY/
        SECRET are not configured. Patents are the strongest costly-signal
        channel (Spence 1973 / Ehrenthal 2026)."""
        docs = collect_patents_for_actor(
            actor_name=actor_name, max_results=max_results, actor_slug=actor_slug
        )
        return json.dumps(docs)

    def register_signal(
        source_url: str,
        title: str,
        summary: str,
        evidence_quote: str,
        dimension: str,
        is_technical: bool,
        confidence: float,
        source_kind: str = "arxiv",
        signal_type: str = "",
    ) -> str:
        signal_buffer.append(
            {
                "actor_slug": actor_slug,
                "source_url": source_url,
                "source_kind": source_kind,
                "title": title,
                "summary": summary,
                "evidence_quote": evidence_quote,
                "dimension": dimension,
                "signal_type": signal_type,  # optional; derive_signal_rows fills it
                "is_technical": bool(is_technical),
                "confidence": float(confidence),
            }
        )
        return json.dumps({"ok": True, "count_so_far": len(signal_buffer)})

    def finish_actor(summary_md: str) -> str:
        return json.dumps({"finished": True, "summary_md_len": len(summary_md or "")})

    registry.add(ToolDef("arxiv_search", "Search arXiv with a free-text query.", arxiv_search,
                         {"query": "string", "max_results": "int (default 5)"}))
    registry.add(ToolDef("website_fetch", "Fetch + extract visible text from one URL.", website_fetch,
                         {"url": "string", "max_pages": "int (default 1)"}))
    registry.add(ToolDef("news_search",
                         "Search Google News for third-party coverage of the actor (Switzerland-biased).",
                         news_search,
                         {"actor_name": "string (the actor's display name)", "max_results": "int (default 5)"}))
    registry.add(ToolDef("press_search",
                         "Search a press-release aggregator (Bing News, PR-flavoured query) for the actor — distinct ranker + sources from news_search; call both for triangulated coverage.",
                         press_search,
                         {"actor_name": "string (the actor's display name)", "max_results": "int (default 5)"}))
    registry.add(ToolDef("patent_search",
                         "EPO Open Patent Services search for quantum-relevant patents naming the actor. Returns [] if EPO_OPS_CONSUMER_KEY/SECRET not configured.",
                         patent_search,
                         {"actor_name": "string (the actor's display name)", "max_results": "int (default 5)"}))
    registry.add(ToolDef("register_signal",
                         "Record one classified signal — call this once per evidence item.",
                         register_signal,
                         {
                             "source_url": "string",
                             "title": "string",
                             "summary": "string",
                             "evidence_quote": "string (verbatim from source)",
                             "dimension": (
                                 "one of (Ehrenthal et al. 2026 four-signal scheme): "
                                 "leadership_expertise, patents, publications, awards, testimonials, "
                                 "educational_outreach, funding_event, regulatory_recognition, "
                                 "collaborations_applications, pilots_pocs, customer_training, "
                                 "cloud_platform_listings, hpc_collaborations, industry_partnerships, "
                                 "academic_partnerships, roadmaps, milestones, technological_advances, "
                                 "long_horizon_claims"
                             ),
                             "signal_type": "one of: legitimacy, customer_cocreation, community_ecosystem, future_trajectory",
                             "is_technical": "bool",
                             "confidence": "float in [0,1]",
                             "source_kind": "arxiv | website | swissreg | manual",
                         }))
    registry.add(ToolDef("finish_actor", "Signal that all signals for the current actor are done and provide a short markdown brief.",
                         finish_actor, {"summary_md": "string"}))
