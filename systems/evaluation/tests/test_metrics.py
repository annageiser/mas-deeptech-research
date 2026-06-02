"""Unit tests for the four metrics on synthetic data.

These tests are hermetic — no Supabase, no LLM. The Supabase-side
production behaviour is verified by the cron + the audit folders.
"""

from __future__ import annotations

import pandas as pd
import pytest

from eval_app.metrics import (
    classification_quality,
    inter_system_agreement,
    reproducibility,
    token_efficiency,
)


# ---------- inter_system_agreement ----------

def test_isa_empty_input() -> None:
    out = inter_system_agreement(pd.DataFrame())
    assert out["n_actors_compared"] == 0
    assert out["jaccard_macro"] is None


def test_isa_perfect_agreement_per_actor() -> None:
    df = pd.DataFrame([
        {"actor_slug": "a1", "system": "masfactory", "source_url": "u1"},
        {"actor_slug": "a1", "system": "masfactory", "source_url": "u2"},
        {"actor_slug": "a1", "system": "hermes",     "source_url": "u1"},
        {"actor_slug": "a1", "system": "hermes",     "source_url": "u2"},
    ])
    out = inter_system_agreement(df)
    assert out["n_actors_compared"] == 1
    assert out["jaccard_macro"] == 1.0
    assert out["per_actor"][0]["n_intersection"] == 2
    assert out["per_actor"][0]["n_union"] == 2


def test_isa_disjoint_actors_are_not_compared() -> None:
    df = pd.DataFrame([
        {"actor_slug": "a1", "system": "masfactory", "source_url": "u1"},
        {"actor_slug": "a2", "system": "hermes",     "source_url": "u9"},
    ])
    out = inter_system_agreement(df)
    # neither actor has signals from BOTH systems
    assert out["n_actors_compared"] == 0
    assert out["actor_buckets"]["only_a"] == 1
    assert out["actor_buckets"]["only_b"] == 1


def test_isa_partial_overlap_jaccard_correct() -> None:
    # A: {u1, u2}; B: {u2, u3}; intersection={u2}; union={u1, u2, u3} -> 1/3
    df = pd.DataFrame([
        {"actor_slug": "a", "system": "masfactory", "source_url": "u1"},
        {"actor_slug": "a", "system": "masfactory", "source_url": "u2"},
        {"actor_slug": "a", "system": "hermes",     "source_url": "u2"},
        {"actor_slug": "a", "system": "hermes",     "source_url": "u3"},
    ])
    out = inter_system_agreement(df)
    assert out["per_actor"][0]["jaccard"] == pytest.approx(1 / 3, abs=1e-4)
    assert out["jaccard_macro"] == pytest.approx(1 / 3, abs=1e-4)


# ---------- token_efficiency ----------

def test_te_basic_computation() -> None:
    signals_df = pd.DataFrame([
        {"system": "masfactory"}, {"system": "masfactory"}, {"system": "masfactory"},
        {"system": "hermes"},
    ])
    tokens_df = pd.DataFrame([
        {"system": "masfactory", "input_tokens": 1000, "output_tokens": 500, "calls": 1},
        {"system": "hermes",     "input_tokens": 4000, "output_tokens": 1000, "calls": 1},
    ])
    out = token_efficiency(signals_df, tokens_df)
    a = out["per_system"]["masfactory"]
    b = out["per_system"]["hermes"]
    assert a["n_signals"] == 3
    assert a["total_tokens"] == 1500
    assert a["signals_per_1k_tokens"] == pytest.approx(3 * 1000 / 1500, abs=1e-4)
    assert b["signals_per_1k_tokens"] == pytest.approx(1 * 1000 / 5000, abs=1e-4)
    # A's efficiency is 2.0 signals/k; B's is 0.2 signals/k; A/B = 10x.
    assert out["ratio_a_over_b"] == pytest.approx(10.0, abs=1e-3)


def test_te_no_tokens_returns_none_efficiency() -> None:
    signals_df = pd.DataFrame([{"system": "masfactory"}])
    tokens_df = pd.DataFrame(columns=["system", "input_tokens", "output_tokens"])
    out = token_efficiency(signals_df, tokens_df)
    assert out["per_system"]["masfactory"]["signals_per_1k_tokens"] is None


# ---------- reproducibility ----------

def test_reproducibility_two_runs_same_cohort() -> None:
    runs_df = pd.DataFrame([
        {"id": "r1", "system": "masfactory", "status": "ok", "started_at": "2026-06-01",
         "actor_slugs": ["a1", "a2"], "config_snapshot": {"x": 1}},
        {"id": "r2", "system": "masfactory", "status": "ok", "started_at": "2026-06-02",
         "actor_slugs": ["a1", "a2"], "config_snapshot": {"x": 1}},
    ])
    signals_df = pd.DataFrame([
        {"run_id": "r1", "actor_slug": "a1", "source_url": "u1"},
        {"run_id": "r1", "actor_slug": "a1", "source_url": "u2"},
        {"run_id": "r2", "actor_slug": "a1", "source_url": "u1"},
        {"run_id": "r2", "actor_slug": "a1", "source_url": "u3"},
    ])
    out = reproducibility(runs_df, signals_df)
    # Intersection {u1}, union {u1, u2, u3} → Jaccard 1/3
    assert out["per_comparison"][0]["jaccard"] == pytest.approx(1 / 3, abs=1e-4)


def test_reproducibility_skips_single_run_cohorts() -> None:
    runs_df = pd.DataFrame([
        {"id": "r1", "system": "masfactory", "status": "ok",
         "started_at": "2026-06-01", "actor_slugs": ["a1"]},
    ])
    signals_df = pd.DataFrame([{"run_id": "r1", "actor_slug": "a1", "source_url": "u1"}])
    out = reproducibility(runs_df, signals_df)
    assert out["per_comparison"] == []
    assert out["per_system"]["masfactory"]["jaccard_mean"] is None


# ---------- classification_quality ----------

def test_cq_no_gold_file_returns_structured_marker(tmp_path) -> None:
    out = classification_quality(pd.DataFrame(), str(tmp_path / "missing.yaml"))
    assert out["status"] == "no_gold_set"


def test_cq_with_gold_computes_metrics(tmp_path) -> None:
    # Two correctly classified, one wrongly classified
    gold_yaml = tmp_path / "labels.yaml"
    gold_yaml.write_text(
        "- signal_id: s1\n  gold_signal_type: legitimacy\n  gold_dimension: patents\n  gold_keep: true\n"
        "- signal_id: s2\n  gold_signal_type: legitimacy\n  gold_dimension: funding_event\n  gold_keep: true\n"
        "- signal_id: s3\n  gold_signal_type: future_trajectory\n  gold_dimension: roadmaps\n  gold_keep: false\n"
    )
    signals_df = pd.DataFrame([
        {"id": "s1", "system": "masfactory", "signal_type": "legitimacy",       "dimension": "patents",        "confidence": 0.9},
        {"id": "s2", "system": "masfactory", "signal_type": "legitimacy",       "dimension": "funding_event",  "confidence": 0.9},
        {"id": "s3", "system": "masfactory", "signal_type": "future_trajectory", "dimension": "milestones",     "confidence": 0.5},  # wrong dim
    ])
    out = classification_quality(signals_df, str(gold_yaml))
    assert out["status"] == "ok"
    assert out["n_matched"] == 3
    # signal_type: all three agree → accuracy 1.0
    st_blk = out["ecosystem_overall"]["signal_type"]
    assert st_blk["accuracy"] == 1.0
    # dimension: 2/3 correct
    dim_blk = out["ecosystem_overall"]["dimension"]
    assert dim_blk["accuracy"] == pytest.approx(2 / 3, abs=1e-4)
