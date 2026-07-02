"""v0.4.43 — LLM-failure short-circuit in generate_daily.

Pre-v0.4.43: when OpenRouter's primary AND fallback both failed on the
narrative synthesis call, the RuntimeError propagated up through
generate_daily → cmd_daily → runner.main() and the process exited 1
without writing any report file. The 2026-07-02 and 2026-07-03 daily
reports for both systems went missing this way, even though signals and
runs were correctly persisted in Supabase.

This module verifies the fail-open replacement:
  - a stub report IS written when the LLM call raises
  - the stub carries the day's real numeric summary + a top-3 signals view
  - the return dict is well-formed (path, tokens, short_circuit tag, error)
  - the pre-existing happy path and zero-signal path are unchanged
"""
from __future__ import annotations

import tempfile
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from reports_system import daily as daily_module
from reports_system.daily import _llm_failure_template, generate_daily


# --------------------------------------------------------------------------
# _llm_failure_template — pure-function tests, no mocking
# --------------------------------------------------------------------------
def test_llm_failure_template_renders_summary_correctly() -> None:
    summary = {
        "run_count": 1, "run_ok": 1, "run_error": 0,
        "actors_total": 40, "actors_with_signals": 21, "signal_count": 139,
        "signal_type_counts": {
            "legitimacy": 38, "customer_cocreation": 17,
            "community_ecosystem": 53, "future_trajectory": 31,
        },
    }
    snapshot = {"signals": [
        {"actor_slug": "id-quantique", "signal_type": "future_trajectory",
         "title": "IDQ announces roadmap", "confidence": 0.95},
        {"actor_slug": "eth-zurich", "signal_type": "legitimacy",
         "title": "SNSF Phase II funding confirmed", "confidence": 0.90},
        {"actor_slug": "gesda", "signal_type": "community_ecosystem",
         "title": "GESDA convenes panel at Davos", "confidence": 0.85},
        # a fourth, lower-confidence signal that should NOT appear in top-3
        {"actor_slug": "csem", "title": "Lower-conf signal", "confidence": 0.20},
    ]}
    body = _llm_failure_template(
        "Hermes System B", "B", "2026-07-02", summary, snapshot,
        "RuntimeError: both models failed: primary(x)=rate_limit; fallback(y)=rate_limit",
    )
    assert "# Hermes System B — Daily report, 2026-07-02" in body
    assert "**Runs:** 1 ok / 0 errors" in body
    assert "**New signals:** 139, across 21 of 40 seeded actors" in body
    assert "legitimacy 38" in body and "customer_cocreation 17" in body
    # Top-3 by confidence; lowest-confidence signal excluded.
    assert "id-quantique" in body and "eth-zurich" in body and "gesda" in body
    assert "csem" not in body
    # LLM error surfaces so the /reports page shows what happened.
    assert "rate_limit" in body
    # v0.4.43 provenance marker.
    assert "v0.4.43 LLM-failure short-circuit" in body


def test_llm_failure_template_top_block_handles_empty_signals() -> None:
    body = _llm_failure_template(
        "System A", "A", "2026-07-02",
        {"run_count": 1, "run_ok": 1, "run_error": 0,
         "actors_total": 40, "actors_with_signals": 0, "signal_count": 0},
        {"signals": []},
        "RuntimeError: both models failed",
    )
    assert "None." in body  # top_block fallback


def test_llm_failure_template_missing_signal_type_counts_render_zeros() -> None:
    """summary without signal_type_counts should still render the mix line
    with zeros rather than raising."""
    body = _llm_failure_template(
        "System A", "A", "2026-07-02",
        {"run_count": 1, "signal_count": 5, "run_ok": 1, "run_error": 0,
         "actors_total": 40, "actors_with_signals": 3},
        {"signals": [{"actor_slug": "eth-zurich", "title": "x", "confidence": 0.5}]},
        "some error",
    )
    assert "legitimacy 0" in body
    assert "community_ecosystem 0" in body


# --------------------------------------------------------------------------
# generate_daily — full-path tests with LLM mocked
# --------------------------------------------------------------------------
def _mock_snapshot_with_signals() -> dict:
    return {
        "summary": {
            "run_count": 1, "run_ok": 1, "run_error": 0,
            "actors_total": 40, "actors_with_signals": 2, "signal_count": 9,
            "signal_type_counts": {
                "legitimacy": 3, "customer_cocreation": 2,
                "community_ecosystem": 2, "future_trajectory": 2,
            },
        },
        "signals": [
            {"actor_slug": "zurich-instruments", "signal_type": "future_trajectory",
             "title": "IQM, Zurich Instruments, and NVIDIA launch real-time QEC demo",
             "confidence": 0.9},
        ],
        "actors_by_slug": {"zurich-instruments": {"name": "Zurich Instruments"}},
    }


def _fake_settings(tmpdir: pathlib.Path) -> object:
    """Minimal Settings-shaped object; only fields the code path reads."""
    s = MagicMock()
    s.reports_dir = str(tmpdir)
    s.model_main = "primary/test"
    s.model_fallback = "fallback/test"
    s.reasoning_exclude = True
    s.openrouter_api_key = "sk-test"
    s.openrouter_base_url = "https://openrouter.ai/api/v1"
    s.http_referer = "https://test"
    s.app_title = "test"
    return s


def test_generate_daily_writes_stub_when_llm_raises(tmp_path: pathlib.Path) -> None:
    """The v0.4.43 short-circuit: when client.chat() raises, a stub report
    file must be written and the return dict must be well-formed."""
    fake_settings = _fake_settings(tmp_path)

    with patch.object(daily_module, "SupabaseReader") as reader_cls, \
         patch.object(daily_module, "render_prompt", return_value="fake prompt"), \
         patch.object(daily_module, "OpenRouterClient") as client_cls:
        reader_cls.return_value.daily_snapshot.return_value = _mock_snapshot_with_signals()
        client_instance = MagicMock()
        client_instance.chat.side_effect = RuntimeError(
            "both models failed: primary(nemotron)=rate_limit; fallback(qwen)=rate_limit"
        )
        client_instance.tally.input_tokens = 0
        client_instance.tally.output_tokens = 0
        client_instance.tally.calls = 0
        client_cls.return_value = client_instance

        result = generate_daily(settings=fake_settings, system="hermes")

    assert result["short_circuit"] == "llm_failure"
    assert "RuntimeError" in result["error"]
    assert "both models failed" in result["error"]
    # File written to disk
    written = pathlib.Path(result["path"])
    assert written.exists()
    body = written.read_text()
    assert "Hermes System B" in body
    assert "**New signals:** 9" in body
    assert "v0.4.43 LLM-failure short-circuit" in body


def test_generate_daily_happy_path_unchanged(tmp_path: pathlib.Path) -> None:
    """Regression: a successful client.chat() still writes the LLM output
    verbatim (no short-circuit tag, no error field)."""
    fake_settings = _fake_settings(tmp_path)

    with patch.object(daily_module, "SupabaseReader") as reader_cls, \
         patch.object(daily_module, "render_prompt", return_value="fake prompt"), \
         patch.object(daily_module, "OpenRouterClient") as client_cls:
        reader_cls.return_value.daily_snapshot.return_value = _mock_snapshot_with_signals()
        client_instance = MagicMock()
        client_instance.chat.return_value = "# Real LLM narrative\n\n Content."
        client_instance.tally.input_tokens = 500
        client_instance.tally.output_tokens = 300
        client_instance.tally.calls = 1
        client_cls.return_value = client_instance

        result = generate_daily(settings=fake_settings, system="hermes")

    assert "short_circuit" not in result
    assert "error" not in result
    body = pathlib.Path(result["path"]).read_text()
    # write_report prepends a generated_at header; the LLM narrative appears below it.
    assert "# Real LLM narrative" in body
    assert "v0.4.43 LLM-failure short-circuit" not in body


def test_generate_daily_zero_signal_path_unchanged(tmp_path: pathlib.Path) -> None:
    """Regression: zero-signal short-circuit still fires before the LLM
    call is even attempted."""
    fake_settings = _fake_settings(tmp_path)
    empty_snapshot = {
        "summary": {"run_count": 1, "run_ok": 1, "run_error": 0,
                    "actors_total": 40, "actors_with_signals": 0, "signal_count": 0},
        "signals": [],
        "actors_by_slug": {},
    }

    with patch.object(daily_module, "SupabaseReader") as reader_cls, \
         patch.object(daily_module, "OpenRouterClient") as client_cls:
        reader_cls.return_value.daily_snapshot.return_value = empty_snapshot
        # If v0.4.43 breaks the zero-signal path, the LLM would be called and
        # this side_effect would raise — the assertion below would fail.
        client_cls.return_value.chat.side_effect = AssertionError("LLM should not be called")

        result = generate_daily(settings=fake_settings, system="masfactory")

    assert result["short_circuit"] == "zero_signals"
    body = pathlib.Path(result["path"]).read_text()
    assert "v0.4.36 zero-signal short-circuit" in body
