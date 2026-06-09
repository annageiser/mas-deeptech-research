"""Industry-news cron entrypoint — fully self-contained.

Fetches the industry / swiss_media / defense RSS groups from
/data/raw/rss_feeds.yaml (bind-mounted into the container) and upserts
each entry into public.industry_news. Idempotent on
(source_url, content_hash) via the table's unique index.

Run from the reports container:
    docker compose run --rm --entrypoint python reports \\
        -m reports_system.industry_news_runner

Why this module is self-contained (no masfactory import): the reports
container's pyproject.toml does not install systems/masfactory. Vendoring
the small RSS-fetch logic here keeps deployment simple — one image, no
cross-system dependency surface.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import feedparser
import httpx
import yaml
from supabase import create_client


log = logging.getLogger("industry_news")


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)


def _config_path() -> Path:
    env = os.environ.get("RPT_RSS_FEEDS_PATH") or os.environ.get("MASF_RSS_FEEDS_PATH")
    if env and os.path.isfile(env):
        return Path(env)
    bind_mount = Path("/data/raw/rss_feeds.yaml")
    if bind_mount.is_file():
        return bind_mount
    raise FileNotFoundError(
        "rss_feeds.yaml not found; set RPT_RSS_FEEDS_PATH or ensure the "
        "data/ host directory is bind-mounted to /data."
    )


def _load_feed_config() -> dict[str, list[dict[str, Any]]]:
    try:
        with open(_config_path(), "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        log.warning("rss_feeds.yaml not found; industry-news collector returns nothing.")
        return {}


def _fetch_feed(url: str, *, timeout: float = 20.0) -> Optional[str]:
    try:
        with httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        log.warning("RSS fetch failed for %s: %s", url, exc)
        return None


def _collect_records(max_entries_per_feed: int = 50) -> list[dict[str, Any]]:
    cfg = _load_feed_config()
    if not cfg:
        return []
    records: list[dict[str, Any]] = []
    for group in ("industry", "swiss_media", "defense"):
        for feed in cfg.get(group, []) or []:
            url = feed.get("url")
            if not url:
                continue
            body = _fetch_feed(url)
            if not body:
                continue
            parsed = feedparser.parse(body)
            for entry in parsed.entries[: max_entries_per_feed]:
                title = (entry.get("title") or "").strip()
                summary = (entry.get("summary") or entry.get("description") or "").strip()
                link = (entry.get("link") or "").strip()
                if not title or not link:
                    continue
                published: Optional[datetime] = None
                try:
                    if entry.get("published_parsed"):
                        published = datetime(*entry["published_parsed"][:6], tzinfo=timezone.utc)
                except Exception:
                    published = None
                body_blob = f"{title}\n\n{summary}"
                records.append({
                    "source_url": link,
                    "source_name": feed.get("name", "unknown"),
                    "title": title[:500],
                    "summary": summary[:2000],
                    "published_at": published.isoformat() if published else None,
                    "content_hash": hashlib.sha256(body_blob.encode("utf-8")).hexdigest(),
                })
    return records


def main(argv: list[str] | None = None) -> int:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        return 2

    records = _collect_records(max_entries_per_feed=50)
    if not records:
        print("industry-news: no records fetched (check rss_feeds.yaml + network)")
        return 0

    client = create_client(url, key)
    try:
        resp = (client.table("industry_news")
                .upsert(records, on_conflict="source_url,content_hash", ignore_duplicates=True)
                .execute())
        new_count = len(resp.data or [])
        print(f"industry-news: {len(records)} fetched, {new_count} new")
    except Exception as exc:
        print(f"industry-news: upsert failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
