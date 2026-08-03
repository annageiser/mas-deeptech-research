"""A token-efficiency ratio is only meaningful if both sides are equally covered.

`public.token_usage` held rows for 99 percent of System A's successful runs but
only 26 percent of System B's, while the signal counts were complete for both.
System B therefore had a near-complete numerator over a quarter-sized
denominator and appeared 8.9x more efficient. The like-for-like figure is about
1.4x.

Root cause: only System A writes token_usage. When System B moved from the
in-house implementation to the upstream Hermes CLI on 2026-06-10, the new
wrapper never recorded tokens, so every System B row in that table predates
2026-06-09 and belongs to a system that no longer runs.

The metric now measures its own coverage and refuses to present the ratio as
trustworthy when the two sides are not comparable.
"""

from __future__ import annotations

import pandas as pd
import pytest

from eval_app.metrics import token_efficiency


def _signals(n_a, n_b):
    return pd.DataFrame(
        [{"system": "masfactory"}] * n_a + [{"system": "hermes"}] * n_b
    )


def _tokens(rows):
    """rows: list of (system, run_id, input, output)."""
    return pd.DataFrame(
        [{"system": s, "run_id": r, "input_tokens": i, "output_tokens": o}
         for s, r, i, o in rows]
    )


def _runs(n_a, n_b):
    return pd.DataFrame(
        [{"id": f"a{i}", "system": "masfactory", "status": "ok"} for i in range(n_a)]
        + [{"id": f"b{i}", "system": "hermes", "status": "ok"} for i in range(n_b)]
    )


def test_the_production_shape_is_flagged_as_not_comparable():
    """The exact situation that produced the 8.9x figure: 99 percent coverage on
    one side, 26 percent on the other."""
    runs = _runs(98, 89)
    toks = _tokens(
        [("masfactory", f"a{i}", 400_000, 240_000) for i in range(97)]
        + [("hermes", f"b{i}", 650_000, 80_000) for i in range(23)]
    )
    out = token_efficiency(_signals(1008, 2335), toks, runs)

    assert out["comparable"] is False
    assert out["warnings"], "a ratio across unequal coverage must carry a warning"
    joined = " ".join(out["warnings"])
    assert "26%" in joined and "System B" in joined
    # the raw numbers stay available, they are just not presented as comparable
    assert out["ratio_a_over_b"] is not None


def test_equal_and_full_coverage_is_comparable():
    runs = _runs(10, 10)
    toks = _tokens(
        [("masfactory", f"a{i}", 100_000, 50_000) for i in range(10)]
        + [("hermes", f"b{i}", 100_000, 50_000) for i in range(10)]
    )
    out = token_efficiency(_signals(100, 200), toks, runs)

    assert out["comparable"] is True
    assert out["warnings"] == []
    assert out["per_system"]["masfactory"]["token_data_coverage"] == 1.0
    assert out["per_system"]["hermes"]["token_data_coverage"] == 1.0


def test_a_moderate_but_equal_shortfall_is_still_flagged():
    """Both at 50 percent is symmetric, so the ratio survives, but each system's
    own efficiency is still overstated and that must be said."""
    runs = _runs(10, 10)
    toks = _tokens(
        [("masfactory", f"a{i}", 100_000, 50_000) for i in range(5)]
        + [("hermes", f"b{i}", 100_000, 50_000) for i in range(5)]
    )
    out = token_efficiency(_signals(100, 100), toks, runs)

    assert out["comparable"] is False
    assert any("50%" in w for w in out["warnings"])


def test_a_coverage_gap_alone_is_enough_to_flag():
    """Both above the floor, but 100 vs 82 percent still skews the ratio."""
    runs = _runs(50, 50)
    toks = _tokens(
        [("masfactory", f"a{i}", 100_000, 50_000) for i in range(50)]
        + [("hermes", f"b{i}", 100_000, 50_000) for i in range(41)]
    )
    out = token_efficiency(_signals(100, 100), toks, runs)

    assert out["comparable"] is False
    assert any("differs between the systems" in w for w in out["warnings"])


def test_without_runs_df_the_check_cannot_run_and_says_so():
    """Backwards compatible: the old two-argument call still works, but it can
    no longer claim the ratio is trustworthy."""
    toks = _tokens([("masfactory", "a0", 100, 50), ("hermes", "b0", 100, 50)])
    out = token_efficiency(_signals(10, 10), toks)

    assert out["comparable"] is False
    assert any("coverage is unknown" in w for w in out["warnings"])
    assert out["ratio_a_over_b"] is not None


def test_coverage_counts_only_successful_runs():
    runs = pd.DataFrame([
        {"id": "a0", "system": "masfactory", "status": "ok"},
        {"id": "a1", "system": "masfactory", "status": "error"},
        {"id": "b0", "system": "hermes", "status": "ok"},
    ])
    toks = _tokens([("masfactory", "a0", 100, 50), ("hermes", "b0", 100, 50)])
    out = token_efficiency(_signals(1, 1), toks, runs)

    assert out["per_system"]["masfactory"]["n_runs"] == 1, "the errored run must not count"
    assert out["per_system"]["masfactory"]["token_data_coverage"] == 1.0


def test_every_warning_points_at_the_recovery_route():
    runs = _runs(10, 10)
    toks = _tokens([("masfactory", f"a{i}", 100, 50) for i in range(10)]
                   + [("hermes", "b0", 100, 50)])
    out = token_efficiency(_signals(10, 10), toks, runs)

    assert any("state.db" in w for w in out["warnings"]), (
        "a reader who hits this needs to be told where System B's real usage lives"
    )


def test_empty_input_does_not_crash():
    out = token_efficiency(pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
    assert out["metric"] == "token_efficiency"
    assert out["per_system"]["masfactory"]["n_signals"] == 0
