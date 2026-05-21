"""Smoke tests for the reports container (no network, no credentials)."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone

import pytest

from reports_system.config import ConfigError, load_settings
from reports_system.output_writer import write_report
from reports_system.prompt_loader import load_prompt
from reports_system.supabase_reader import _summarise


def test_all_three_prompts_load():
    for name in ("daily", "weekly_system", "weekly_thesis"):
        body = load_prompt(name)
        assert len(body) > 100
        assert "## " in body  # has at least one markdown section


def test_settings_require_openrouter(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        load_settings(require_supabase=False)


def test_settings_minimum(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    s = load_settings(require_supabase=False)
    assert s.openrouter_api_key == "test"
    assert s.model_main.startswith("nvidia/nemotron")
    assert s.reports_dir.endswith("reports")


def test_summarise_empty_input():
    summary = _summarise([], [], [], {})
    assert summary["run_count"] == 0
    assert summary["signal_count"] == 0
    assert summary["actors_with_signals"] == 0
    assert summary["actors_total"] == 0


def test_summarise_with_data():
    actors = {"a1": {"name": "Actor 1"}, "a2": {"name": "Actor 2"}}
    runs = [{"id": "r1", "status": "ok"}, {"id": "r2", "status": "error"}]
    signals = [
        {"run_id": "r1", "actor_slug": "a1", "dimension": "research_output", "is_technical": True},
        {"run_id": "r1", "actor_slug": "a1", "dimension": "research_output", "is_technical": True},
        {"run_id": "r1", "actor_slug": "a2", "dimension": "funding_or_grant", "is_technical": False},
    ]
    tokens = [
        {"run_id": "r1", "input_tokens": 100, "output_tokens": 50, "calls": 3},
        {"run_id": "r2", "input_tokens": 20, "output_tokens": 10, "calls": 1},
    ]
    s = _summarise(runs, signals, tokens, actors)
    assert s["run_count"] == 2
    assert s["run_ok"] == 1
    assert s["run_error"] == 1
    assert s["signal_count"] == 3
    assert s["by_dimension"] == {"research_output": 2, "funding_or_grant": 1}
    assert s["by_technical"] == {"technical": 2, "non-technical": 1}
    assert s["actors_with_signals"] == 2
    assert s["actors_total"] == 2
    assert s["total_input_tokens"] == 120
    assert s["total_output_tokens"] == 60
    assert s["total_calls"] == 4
    assert s["top_actors_by_signal_count"][0] == ("a1", 2)


def test_write_report_creates_file_and_header():
    with tempfile.TemporaryDirectory() as tmp:
        path = write_report(tmp, "daily/2026-05-21", "masfactory.md", "# Test report\n\nBody.")
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        assert "generated_at:" in content
        assert "# Test report" in content
        assert content.endswith("Body.\n")
