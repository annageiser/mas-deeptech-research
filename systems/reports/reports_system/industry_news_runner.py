"""Industry-news cron entrypoint.

Fetches the industry / swiss_media / defense RSS groups (unattributed) and
upserts each entry into public.industry_news. Idempotent on
(source_url, content_hash).

Run from the same `reports` container as the daily/weekly synthesis:
    python -m reports_system.industry_news_runner

Configured to run hourly via the cron config so the /quantum-news page
stays fresh independent of the per-actor scrape schedule.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    # Lazy import so the masfactory collector module is only loaded when
    # this entrypoint is actually invoked.
    try:
        from masfactory_system.collection.rss import collect_industry_news_unattributed
    except ImportError:
        # If masfactory isn't installed in this container, install or
        # vendor the module — for v0.4.3 we share the reports container
        # so the import works because both are co-installed.
        print("masfactory_system.collection.rss not importable in this container", file=sys.stderr)
        return 2

    from supabase import create_client
    import os
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        return 2
    client = create_client(url, key)

    records = collect_industry_news_unattributed(max_entries_per_feed=50)
    if not records:
        print("industry-news: no records fetched")
        return 0

    # Idempotent upsert on (source_url, content_hash). New entries appear;
    # repeats are silently skipped. The unique index in schema.sql guarantees
    # correctness even under concurrent runs.
    try:
        resp = (client.table("industry_news")
                .upsert(records, on_conflict="source_url,content_hash", ignore_duplicates=True)
                .execute())
        print(f"industry-news: {len(records)} fetched, {len(resp.data or [])} new")
    except Exception as exc:
        print(f"industry-news: upsert failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
