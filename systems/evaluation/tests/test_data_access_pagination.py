"""Regression tests for the PostgREST 1000-row truncation in the eval harness.

This is the copy that matters most. `eval_app.runner` pulls `signals`, `runs`
and `token_usage` once and shares the frames across all four thesis metrics, so
a silently truncated frame silently truncates every published number.

PostgREST caps a response at `max-rows` (1000 on Supabase) and returns a PARTIAL
result with HTTP 200 and no error. The fetches used to call .execute() with no
.range() window. At the time this was found, the live 90-day window held 3238
signals, so the harness was computing on 1000 of them.

Hermetic: a fake client reproduces the cap. No Supabase, no network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from eval_app import data_access as da


SERVER_MAX_ROWS = 1000


class FakeResponse:
    def __init__(self, data: list[dict], count: int | None):
        self.data = data
        self.count = count


class FakeQuery:
    """Stand-in for a postgrest builder that enforces the server row cap."""

    def __init__(self, rows: list[dict], stats: dict, *, report_count: bool = True):
        self._rows = rows
        self._stats = stats
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

    def eq(self, column, value):
        self._rows = [r for r in self._rows if r.get(column) == value]
        return self

    def in_(self, column, values):
        allowed = set(values)
        self._rows = [r for r in self._rows if r.get(column) in allowed]
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
        window = rows if self._end is None else rows[self._start:self._end + 1]
        return FakeResponse(
            window[:SERVER_MAX_ROWS],
            total if (self._count_requested and self._report_count) else None,
        )


class FakeClient:
    def __init__(self, tables: dict[str, list[dict]], stats: dict, **kwargs):
        self._tables, self._stats, self._kwargs = tables, stats, kwargs

    def table(self, name):
        return FakeQuery(list(self._tables.get(name, [])), self._stats, **self._kwargs)


def _install(monkeypatch, tables, **kwargs):
    stats = {"requests": 0}
    monkeypatch.setattr(da, "client", lambda: FakeClient(tables, stats, **kwargs))
    return stats


def _signals(n: int, *, hermes: int | None = None) -> list[dict]:
    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        system = ("hermes" if i < hermes else "masfactory") if hermes is not None \
            else ("hermes" if i % 2 else "masfactory")
        out.append({
            "id": f"s{i:06d}", "run_id": f"r{i // 100}", "actor_slug": f"a{i % 40}",
            "system": system, "source_kind": "news", "source_url": f"https://x/{i}",
            "title": f"t{i}", "summary": "", "evidence_quote": "",
            "dimension": "funding_event", "signal_type": "legitimacy",
            "dimension_legacy": None, "is_technical": False, "confidence": 0.8,
            # Whole blocks share a timestamp, as a real cron tick does.
            "inserted_at": (base - timedelta(days=i // 200)).isoformat(),
        })
    return out


def test_signals_survive_the_server_cap(monkeypatch):
    """3238 is the live 90-day corpus size that exposed the bug."""
    rows = _signals(3238)
    _install(monkeypatch, {"signals": rows})

    df = da.signals(days=90)

    assert len(df) == 3238, "pre-fix behaviour returned exactly 1000"
    assert set(df["id"]) == {r["id"] for r in rows}


def test_no_duplicates_across_page_boundaries(monkeypatch):
    _install(monkeypatch, {"signals": _signals(2500)})
    df = da.signals(days=90)
    assert len(df) == len(set(df["id"])) == 2500


def test_ab_ratio_matches_the_window_not_the_tail(monkeypatch):
    """The metric-level consequence. Truncation kept the newest rows; the two
    producers' output rates differ over time, so inter-system agreement and
    token efficiency were computed on a recency-skewed slice."""
    _install(monkeypatch, {"signals": _signals(3000, hermes=2200)})

    df = da.signals(days=90)
    counts = df["system"].value_counts().to_dict()

    assert counts == {"hermes": 2200, "masfactory": 800}


def test_system_filter_still_applies(monkeypatch):
    _install(monkeypatch, {"signals": _signals(3000, hermes=2200)})
    df = da.signals(system="masfactory", days=90)
    assert len(df) == 800
    assert set(df["system"]) == {"masfactory"}


def test_empty_and_single_page(monkeypatch):
    _install(monkeypatch, {"signals": []})
    assert da.signals(days=90).empty

    stats = _install(monkeypatch, {"signals": _signals(50)})
    assert len(da.signals(days=90)) == 50
    assert stats["requests"] == 1, "an exact count avoids a tail probe"


def test_runs_pages(monkeypatch):
    runs = [{"id": f"r{i:05d}", "system": "hermes", "status": "ok",
             "started_at": f"2026-07-{(i % 28) + 1:02d}T00:00:00+00:00",
             "finished_at": None, "actor_slugs": [], "error_message": None}
            for i in range(1300)]
    _install(monkeypatch, {"runs": runs})

    df = da.runs(days=90)

    assert len(df) == 1300
    assert len(set(df["id"])) == 1300


def test_token_usage_pages_within_each_run_id_chunk(monkeypatch):
    """token_usage already chunked its IN-clause at 100 run ids, but each chunk
    was itself unpaged. A multi-node graph over 100 runs clears 1000 rows on its
    own, so the per-chunk fetch needed paging too."""
    runs = [{"id": f"r{i:04d}", "system": "hermes" if i % 2 else "masfactory",
             "status": "ok", "started_at": "2026-07-15T00:00:00+00:00",
             "finished_at": None, "actor_slugs": [], "error_message": None}
            for i in range(120)]
    tokens = [{"id": f"t{i:05d}", "run_id": f"r{i % 120:04d}", "node_name": f"n{i % 15}",
               "model_name": "m", "input_tokens": 10, "output_tokens": 5, "calls": 1}
              for i in range(1800)]
    _install(monkeypatch, {"runs": runs, "token_usage": tokens})

    df = da.token_usage(days=90)

    assert len(df) == 1800, "every token row must survive both the chunking and the cap"
    assert set(df["system"].dropna()) == {"hermes", "masfactory"}


def test_no_count_header_fallback(monkeypatch):
    """Deployments that do not return Content-Range still page correctly."""
    _install(monkeypatch, {"signals": _signals(2300)}, report_count=False)
    assert len(da.signals(days=90)) == 2300


def test_safety_cap_bounds_the_loop(monkeypatch):
    _install(monkeypatch, {"signals": _signals(5000)})
    collected = da._paged(
        lambda: da.client().table("signals").select("id", count="exact").order("id"),
        max_rows=1500,
    )
    assert len(collected) == 1500


def test_dedupe_helper():
    assert [r["id"] for r in da._dedupe_by_id(
        [{"id": "a"}, {"id": "b"}, {"id": "b"}, {"id": "c"}]
    )] == ["a", "b", "c"]
    # actors is keyed on slug, not id; those rows must pass through untouched.
    assert da._dedupe_by_id([{"slug": "x"}, {"slug": "y"}]) == [{"slug": "x"}, {"slug": "y"}]


@pytest.mark.parametrize("n", [999, 1000, 1001, 2000, 2001])
def test_page_boundary_sizes(monkeypatch, n):
    _install(monkeypatch, {"signals": _signals(n)})
    assert len(da.signals(days=90)) == n
