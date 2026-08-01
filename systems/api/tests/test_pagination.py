"""Regression tests for the PostgREST 1000-row truncation.

Background: PostgREST enforces a server-side `max-rows` cap (1000 on Supabase)
and returns a PARTIAL result with HTTP 200 and no error. Every fetch in
data_access.py used to call .execute() without a .range() window, so once a
table passed 1000 matching rows the remainder was dropped silently. Because the
signal queries order by `inserted_at desc`, the surviving slice was always the
newest rows, which is not a random sample of the corpus.

These tests drive data_access against a fake client that reproduces the cap, so
they fail on the pre-fix code and pass on the paged version. No network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from api_app import data_access as da


SERVER_MAX_ROWS = 1000


class FakeResponse:
    def __init__(self, data: list[dict], count: int | None):
        self.data = data
        self.count = count


class FakeQuery:
    """Minimal stand-in for a postgrest SyncSelectRequestBuilder.

    Applies the two behaviours that matter: the server-side row cap, and
    offset/limit windowing via .range(). Every filter is a no-op except `eq`,
    which the system-scoped fetches rely on.
    """

    def __init__(self, rows: list[dict], stats: dict, *, max_rows: int = SERVER_MAX_ROWS,
                 report_count: bool = True):
        self._rows = rows
        self._stats = stats
        self._max_rows = max_rows
        self._report_count = report_count
        self._count_requested = False
        self._start = 0
        self._end: int | None = None
        self._order: list[tuple[str, bool]] = []

    def select(self, *columns, count=None, head=None):
        self._count_requested = count is not None
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def not_(self, *_args, **_kwargs):  # pragma: no cover - shape only
        return self

    def is_(self, *_args, **_kwargs):  # pragma: no cover - shape only
        return self

    def in_(self, column, values):
        self._rows = [r for r in self._rows if r.get(column) in set(values)]
        return self

    def eq(self, column, value):
        self._rows = [r for r in self._rows if r.get(column) == value]
        return self

    def order(self, column, desc=False, **_kwargs):
        self._order.append((column, desc))
        return self

    def range(self, start, end, **_kwargs):
        self._start, self._end = start, end
        return self

    def execute(self):
        self._stats["requests"] += 1
        rows = list(self._rows)
        for column, desc in reversed(self._order):
            rows.sort(key=lambda r: (r.get(column) is None, r.get(column)), reverse=desc)
        total = len(rows)

        if self._end is None:
            window = rows
        else:
            window = rows[self._start:self._end + 1]
        # The behaviour under test: the server silently truncates.
        truncated = window[:self._max_rows]
        self._stats["max_returned"] = max(self._stats["max_returned"], len(truncated))
        return FakeResponse(truncated, total if (self._count_requested and self._report_count) else None)


class FakeClient:
    def __init__(self, tables: dict[str, list[dict]], stats: dict, **kwargs):
        self._tables = tables
        self._stats = stats
        self._kwargs = kwargs

    def table(self, name):
        # A fresh builder per call, which is exactly what _paged relies on.
        return FakeQuery(list(self._tables.get(name, [])), self._stats, **self._kwargs)


def _signal_rows(n: int, *, system_split: tuple[int, int] | None = None) -> list[dict]:
    """n signals, newest first by inserted_at.

    Every row in a real cron tick lands with a near-identical inserted_at, so
    the fixture deliberately gives whole blocks of rows the same timestamp. That
    is what makes the `id` tiebreaker load-bearing.
    """
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        if system_split is None:
            system = "masfactory" if i % 2 else "hermes"
        else:
            system = "hermes" if i < system_split[0] else "masfactory"
        rows.append({
            "id": f"s{i:06d}",
            "run_id": f"r{i // 100}",
            "actor_slug": f"a{i % 40}",
            "system": system,
            "source_kind": "news",
            "source_url": f"https://x/{i}",
            "title": f"t{i}",
            "summary": "",
            "evidence_quote": "",
            "dimension": "funding_event",
            "is_technical": False,
            "confidence": 0.8,
            # One timestamp per block of 200 rows: ties across page boundaries.
            "inserted_at": (base - timedelta(days=i // 200)).isoformat(),
            "sentiment_score": None,
            "sentiment_label": None,
        })
    return rows


@pytest.fixture(autouse=True)
def _clear_cache():
    da._cache.clear()
    yield
    da._cache.clear()


def _install(monkeypatch, tables, **kwargs):
    stats = {"requests": 0, "max_returned": 0}
    monkeypatch.setattr(da, "client", lambda: FakeClient(tables, stats, **kwargs))
    return stats


# ---------- the regression itself ----------

def test_signals_returns_every_row_past_the_server_cap(monkeypatch):
    """3238 rows is the live 90-day corpus size that exposed this."""
    rows = _signal_rows(3238)
    stats = _install(monkeypatch, {"signals": rows})

    df = da.signals(days=90)

    assert len(df) == 3238, "pre-fix behaviour returned exactly the 1000-row cap"
    assert stats["max_returned"] <= SERVER_MAX_ROWS, "fixture must enforce the cap"
    assert stats["requests"] == 4, "3238 rows over a 1000-row page size is 4 requests"


def test_signals_no_duplicate_ids_across_pages(monkeypatch):
    rows = _signal_rows(2500)
    _install(monkeypatch, {"signals": rows})

    df = da.signals(days=90)

    assert len(df) == len(set(df["id"])), "page boundaries must not repeat rows"
    assert set(df["id"]) == {r["id"] for r in rows}, "every row must survive paging"


def test_system_ratio_is_not_skewed_by_truncation(monkeypatch):
    """The reason this bug mattered: truncation kept the newest rows, and the
    two producers' output rates differ over time, so the A-vs-B ratio measured
    on a truncated slice did not match the ratio over the window."""
    rows = _signal_rows(3000, system_split=(2200, 800))
    _install(monkeypatch, {"signals": rows})

    df = da.signals(days=90)

    counts = df["system"].value_counts().to_dict()
    assert counts["hermes"] == 2200
    assert counts["masfactory"] == 800


def test_single_page_result_costs_one_request(monkeypatch):
    """The exact server count means a small result needs no probe request."""
    stats = _install(monkeypatch, {"signals": _signal_rows(120)})

    df = da.signals(days=90)

    assert len(df) == 120
    assert stats["requests"] == 1


def test_exactly_one_full_page(monkeypatch):
    """Boundary: len(rows) == page size. Must not stop one page early, and must
    not loop forever."""
    stats = _install(monkeypatch, {"signals": _signal_rows(SERVER_MAX_ROWS)})

    df = da.signals(days=90)

    assert len(df) == SERVER_MAX_ROWS
    assert stats["requests"] == 1, "the exact count already says there is nothing more"


def test_empty_table(monkeypatch):
    _install(monkeypatch, {"signals": []})
    assert da.signals(days=90).empty


def test_system_filter_applies_before_paging(monkeypatch):
    rows = _signal_rows(3000, system_split=(2200, 800))
    _install(monkeypatch, {"signals": rows})

    df = da.signals(system="masfactory", days=90)

    assert len(df) == 800
    assert set(df["system"]) == {"masfactory"}


# ---------- _paged itself ----------

def test_paged_falls_back_when_server_reports_no_count(monkeypatch):
    """Not every deployment returns Content-Range. Without a count, _paged keeps
    asking until a page comes back short."""
    rows = _signal_rows(2300)
    stats = _install(monkeypatch, {"signals": rows}, report_count=False)

    df = da.signals(days=90)

    assert len(df) == 2300
    assert stats["requests"] == 3, "1000 + 1000 + 300; the short page ends it"


def test_paged_without_count_on_an_exact_multiple(monkeypatch):
    """Worst case for the no-count path: the total is an exact multiple of the
    page size, so the only way to learn there is nothing more is an empty page."""
    stats = _install(monkeypatch, {"signals": _signal_rows(2000)}, report_count=False)

    df = da.signals(days=90)

    assert len(df) == 2000
    assert stats["requests"] == 3, "two full pages plus one empty probe" 


def test_paged_respects_the_safety_cap(monkeypatch):
    rows = _signal_rows(5000)
    _install(monkeypatch, {"signals": rows})
    monkeypatch.setattr(da, "MAX_ROWS", 2000)

    collected = da._paged(
        lambda: da.client().table("signals").select("id", count="exact").order("id"),
        max_rows=2000,
    )

    assert len(collected) == 2000, "hard stop must bound an unbounded count"


def test_paged_deduplicates_an_overlapping_window(monkeypatch):
    """A concurrent insert between two page requests can shift the window and
    resend a row. Dedupe by id makes that harmless."""
    duplicated = [{"id": "x1"}, {"id": "x2"}, {"id": "x2"}, {"id": "x3"}]
    assert [r["id"] for r in da._dedupe_by_id(duplicated)] == ["x1", "x2", "x3"]


def test_dedupe_passes_through_rows_without_an_id():
    """actors is keyed on `slug`, not `id`; those rows must not be dropped."""
    rows = [{"slug": "a1"}, {"slug": "a2"}]
    assert da._dedupe_by_id(rows) == rows


# ---------- the other paged fetches ----------

def test_runs_pages(monkeypatch):
    runs = [{"id": f"r{i:05d}", "system": "hermes", "status": "ok",
             "started_at": f"2026-07-{(i % 28) + 1:02d}T00:00:00+00:00",
             "finished_at": None, "actor_slugs": [], "error_message": None,
             "config_snapshot": {}} for i in range(1500)]
    _install(monkeypatch, {"runs": runs})

    df = da.runs(days=90)

    assert len(df) == 1500
    assert len(set(df["id"])) == 1500


def test_actors_pages(monkeypatch):
    actors = [{"slug": f"a{i:05d}", "name": f"n{i}", "category": "private_company",
               "homepage": None, "arxiv_query": None, "notes": None} for i in range(1200)]
    _install(monkeypatch, {"actors": actors})

    df = da.actors()

    assert len(df) == 1200


def test_token_usage_pages_and_joins_system(monkeypatch):
    tokens = [{"id": f"t{i:05d}", "run_id": f"r{i % 150}", "node_name": "graph_total",
               "model_name": "m", "input_tokens": 10, "output_tokens": 5, "calls": 1,
               "recorded_at": "2026-07-15T00:00:00+00:00"} for i in range(1400)]
    runs = [{"id": f"r{i}", "system": "hermes" if i % 2 else "masfactory"} for i in range(150)]
    _install(monkeypatch, {"token_usage": tokens, "runs": runs})

    df = da.token_usage(days=90)

    assert len(df) == 1400, "token rows must survive the cap too"
    assert set(df["system"].dropna()) == {"hermes", "masfactory"}, "run join must still work"
