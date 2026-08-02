"""Reproducibility must compare what a run FOUND, not what it inserted.

The database-backed metric compares signals attached to each run_id. Signals
attach to the run that FIRST inserted them, and the unique key on
(actor_slug, source_url, content_hash, system) means a re-run that rediscovers
the same URL inserts nothing, so its run_id carries zero rows.

Consecutive runs' inserted sets are therefore near-disjoint by construction.
On the production corpus System A's two most recent runs both attached zero
signals, which is why the metric reported zero comparisons for it; System B's
0.155 was depressed the same way. Both figures describe the deduplicating
store, not the systems.

These tests pin the corrected metric: found sets, consecutive runs, restricted
to the actors both runs attempted.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from eval_app.found_sets import (
    RunFoundSet,
    load_hermes_found_sets,
    load_masfactory_found_sets,
)
from eval_app.metrics import reproducibility_from_found_sets


T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _run(system, key, pairs, actors=None, offset_days=0):
    return RunFoundSet(
        system=system,
        run_key=key,
        started_at=T0 + timedelta(days=offset_days),
        pairs=set(pairs),
        actors=set(actors) if actors is not None else {a for a, _ in pairs},
    )


# ---------- the metric ----------

def test_identical_reruns_score_one():
    pairs = [("a1", "u1"), ("a1", "u2")]
    out = reproducibility_from_found_sets([
        _run("masfactory", "r1", pairs, offset_days=0),
        _run("masfactory", "r2", pairs, offset_days=1),
    ])
    assert out["per_system"]["masfactory"]["jaccard_mean"] == 1.0


def test_disjoint_reruns_score_zero():
    out = reproducibility_from_found_sets([
        _run("masfactory", "r1", [("a1", "u1")], offset_days=0),
        _run("masfactory", "r2", [("a1", "u9")], offset_days=1),
    ])
    assert out["per_system"]["masfactory"]["jaccard_mean"] == 0.0


def test_half_overlap():
    out = reproducibility_from_found_sets([
        _run("masfactory", "r1", [("a1", "u1"), ("a1", "u2")], offset_days=0),
        _run("masfactory", "r2", [("a1", "u2"), ("a1", "u3")], offset_days=1),
    ])
    # intersection 1, union 3
    assert out["per_system"]["masfactory"]["jaccard_mean"] == pytest.approx(1 / 3, abs=1e-4)


def test_system_a_is_measurable_even_when_it_inserts_nothing():
    """The whole point. Two runs that rediscover the same URLs insert zero rows
    each, so the database metric sees nothing, but their found sets are
    identical and reproducibility is 1.0."""
    same = [("a1", "u1"), ("a2", "u2"), ("a3", "u3")]
    out = reproducibility_from_found_sets([
        _run("masfactory", "night1", same, offset_days=0),
        _run("masfactory", "night2", same, offset_days=1),
        _run("masfactory", "night3", same, offset_days=2),
    ])
    st = out["per_system"]["masfactory"]
    assert st["n_comparisons"] == 2
    assert st["jaccard_mean"] == 1.0


def test_comparison_is_restricted_to_the_shared_cohort():
    """A run that attempted 40 actors and one that attempted 3 must be compared
    only over the 3, or a cohort difference reads as non-determinism."""
    a = _run("hermes", "r1", [("a1", "u1"), ("a2", "u2")], actors=["a1", "a2"], offset_days=0)
    b = _run("hermes", "r2", [("a1", "u1")], actors=["a1"], offset_days=1)
    out = reproducibility_from_found_sets([a, b])
    comp = out["per_comparison"][0]
    assert comp["n_shared_actors"] == 1
    assert comp["jaccard"] == 1.0, "a2 is outside the shared cohort and must not count"


def test_empty_runs_do_not_inflate_the_mean():
    """Two runs that found nothing are trivially identical. Counting that as
    Jaccard 1.0 would make a broken system look perfectly reproducible."""
    out = reproducibility_from_found_sets([
        _run("hermes", "empty1", [], actors=["a1"], offset_days=0),
        _run("hermes", "empty2", [], actors=["a1"], offset_days=1),
        _run("hermes", "real1", [("a1", "u1")], offset_days=2),
        _run("hermes", "real2", [("a1", "u1")], offset_days=3),
    ])
    st = out["per_system"]["hermes"]
    assert st["n_comparisons"] == 1, "only the pair of non-empty runs is comparable"
    assert st["jaccard_mean"] == 1.0
    assert st["n_runs_seen"] == 4 and st["n_runs_with_findings"] == 2


def test_systems_are_scored_separately():
    out = reproducibility_from_found_sets([
        _run("masfactory", "m1", [("a1", "u1")], offset_days=0),
        _run("masfactory", "m2", [("a1", "u1")], offset_days=1),
        _run("hermes", "h1", [("a1", "u1")], offset_days=0),
        _run("hermes", "h2", [("a1", "u9")], offset_days=1),
    ])
    assert out["per_system"]["masfactory"]["jaccard_mean"] == 1.0
    assert out["per_system"]["hermes"]["jaccard_mean"] == 0.0


def test_runs_are_ordered_chronologically_not_by_directory_name():
    out = reproducibility_from_found_sets([
        _run("masfactory", "zzz", [("a1", "u2")], offset_days=2),
        _run("masfactory", "aaa", [("a1", "u1")], offset_days=0),
        _run("masfactory", "mmm", [("a1", "u1")], offset_days=1),
    ])
    first = out["per_comparison"][0]
    assert (first["run_a"], first["run_b"]) == ("aaa", "mmm")


def test_no_runs_at_all():
    out = reproducibility_from_found_sets([])
    assert out["per_system"] == {} and out["per_comparison"] == []


# ---------- the loaders ----------

def test_masfactory_loader_reads_the_found_set(tmp_path):
    d = tmp_path / "2026-07-15T04-00-11+0200"
    d.mkdir()
    (d / "final_attributes.json").write_text(json.dumps({
        "run_id": "abc-123",
        "actor_pool": [{"slug": "a1"}, {"slug": "a2"}, {"slug": "a3"}],
        "all_surviving_signals": [
            {"actor_slug": "a1", "source_url": "https://X.test/One/"},
            {"actor_slug": "a2", "source_url": "https://y.test/two"},
            {"actor_slug": "a2", "source_url": ""},          # unusable, dropped
            "not-a-dict",                                     # tolerated
        ],
    }), encoding="utf-8")

    runs = load_masfactory_found_sets(tmp_path)

    assert len(runs) == 1
    r = runs[0]
    assert r.system == "masfactory" and r.run_id == "abc-123"
    assert r.pairs == {("a1", "https://x.test/one"), ("a2", "https://y.test/two")}
    assert r.actors == {"a1", "a2", "a3"}, "falls back to actor_pool when documents_by_actor is absent"
    assert r.started_at is not None and r.started_at.day == 15


def test_masfactory_loader_tolerates_a_corrupt_folder(tmp_path):
    good = tmp_path / "2026-07-15T04-00-11+0200"; good.mkdir()
    (good / "final_attributes.json").write_text(
        json.dumps({"run_id": "ok", "all_surviving_signals":
                    [{"actor_slug": "a1", "source_url": "u"}]}), encoding="utf-8")
    bad = tmp_path / "2026-07-16T04-00-11+0200"; bad.mkdir()
    (bad / "final_attributes.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "no-attrs").mkdir()

    runs = load_masfactory_found_sets(tmp_path)

    assert [r.run_id for r in runs] == ["ok"]


def test_masfactory_loader_missing_dir_is_not_fatal(tmp_path):
    assert load_masfactory_found_sets(tmp_path / "nope") == []


def test_url_normalisation_is_conservative():
    from eval_app.found_sets import _norm_url
    assert _norm_url("https://A.test/Path/") == "https://a.test/path"
    # query strings and www are NOT stripped: merging them would silently
    # inflate the reproducibility figure.
    assert _norm_url("https://a.test/p?x=1") != _norm_url("https://a.test/p")
    assert _norm_url("https://www.a.test/p") != _norm_url("https://a.test/p")


def test_hermes_loader_uses_the_real_parser(tmp_path):
    """Loaded by path from systems/hermes so the found set is exactly what the
    persister saw."""
    from pathlib import Path
    persister = (Path(__file__).resolve().parents[3]
                 / "systems" / "hermes" / "scripts" / "persist_signals.py")
    if not persister.is_file():
        pytest.skip("hermes persister not reachable outside a checkout")

    d = tmp_path / "20260715T050000Z"
    d.mkdir()
    (d / "actors.tsv").write_text("a1\tActor One\t\thttps://a1.test\tprivate_company\n"
                                  "a2\tActor Two\t\thttps://a2.test\tgovernment\n",
                                  encoding="utf-8")
    (d / "a1.stdout.txt").write_text(
        'preamble noise\n```json\n'
        + json.dumps({"signals": [
            {"title": "t", "source_url": "https://a1.test/news/1"},
            {"title": "u", "source_url": "https://a1.test/news/2"},
        ]})
        + '\n```\ntrailing\n', encoding="utf-8")
    (d / "a2.stdout.txt").write_text("the agent produced no block at all\n", encoding="utf-8")

    runs = load_hermes_found_sets(tmp_path, persister_path=persister)

    assert len(runs) == 1
    r = runs[0]
    assert r.system == "hermes"
    assert r.pairs == {("a1", "https://a1.test/news/1"), ("a1", "https://a1.test/news/2")}
    assert r.actors == {"a1", "a2"}, "cohort comes from actors.tsv, including the barren one"


def test_hermes_loader_folds_the_fallback_retry_into_one_actor(tmp_path):
    from pathlib import Path
    persister = (Path(__file__).resolve().parents[3]
                 / "systems" / "hermes" / "scripts" / "persist_signals.py")
    if not persister.is_file():
        pytest.skip("hermes persister not reachable outside a checkout")

    d = tmp_path / "20260715T050000Z"; d.mkdir()
    (d / "a1.stdout.txt").write_text(
        "```json\n" + json.dumps({"signals": []}) + "\n```", encoding="utf-8")
    (d / "a1.fallback.stdout.txt").write_text(
        "```json\n" + json.dumps({"signals": [{"source_url": "https://a1.test/x"}]})
        + "\n```", encoding="utf-8")

    runs = load_hermes_found_sets(tmp_path, persister_path=persister)

    assert runs[0].pairs == {("a1", "https://a1.test/x")}, (
        "the L3 fallback retry belongs to the same actor, not a separate one"
    )


def test_hermes_loader_degrades_when_the_parser_is_absent(tmp_path):
    assert load_hermes_found_sets(tmp_path, persister_path=tmp_path / "nope.py") == []


def test_cohort_is_what_was_processed_not_the_full_roster(tmp_path):
    """actor_pool is the full 40-actor roster regardless of --limit-actors, so
    a one-actor smoke run would otherwise look like a forty-actor run that
    found nothing and would drag every neighbouring comparison down."""
    d = tmp_path / "2026-08-02T02-11-15+0200"
    d.mkdir()
    (d / "final_attributes.json").write_text(json.dumps({
        "run_id": "smoke",
        "limit_actors": 1,
        "actor_pool": [{"slug": f"a{i}"} for i in range(40)],
        "documents_by_actor": [{"actor_slug": "a7", "documents": []}],
        "all_surviving_signals": [{"actor_slug": "a7", "source_url": "https://x/1"}],
    }), encoding="utf-8")

    r = load_masfactory_found_sets(tmp_path)[0]

    assert r.actors == {"a7"}, "a --limit-actors run must not claim the whole roster"
