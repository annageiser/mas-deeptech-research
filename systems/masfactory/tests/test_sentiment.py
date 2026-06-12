"""Tests for v0.4.24 — VADER sentiment scoring (task C.4)."""

from __future__ import annotations

import pytest

from masfactory_system import sentiment


def test_default_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_SENTIMENT", raising=False)
    assert sentiment.is_enabled() is True


def test_explicit_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("0", "false", "no", "off", "FALSE", "  off  "):
        monkeypatch.setenv("MASF_SENTIMENT", value)
        assert sentiment.is_enabled() is False, f"failed for value={value!r}"


def test_anything_else_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("", "1", "yes", "anything-else"):
        monkeypatch.setenv("MASF_SENTIMENT", value)
        assert sentiment.is_enabled() is True, f"failed for value={value!r}"


def test_compose_uses_evidence_and_summary() -> None:
    text = sentiment.compose_sentiment_text({
        "title": "headline shouldnt appear",
        "evidence_quote": "evidence here",
        "summary": "summary here",
    })
    assert "evidence here" in text
    assert "summary here" in text
    assert "headline" not in text


def test_compose_handles_missing_fields() -> None:
    assert sentiment.compose_sentiment_text({}) == ""
    assert sentiment.compose_sentiment_text({"summary": "only summary"}) == "only summary"


def test_label_for_positive() -> None:
    assert sentiment.label_for(0.5) == "positive"
    assert sentiment.label_for(sentiment.POS_THRESHOLD) == "positive"


def test_label_for_negative() -> None:
    assert sentiment.label_for(-0.5) == "negative"
    assert sentiment.label_for(sentiment.NEG_THRESHOLD) == "negative"


def test_label_for_neutral() -> None:
    assert sentiment.label_for(0.0) == "neutral"
    assert sentiment.label_for(0.01) == "neutral"
    assert sentiment.label_for(-0.01) == "neutral"


def test_label_for_none() -> None:
    assert sentiment.label_for(None) is None


def test_score_signal_returns_none_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_SENTIMENT", "0")
    out = sentiment.score_signal({
        "evidence_quote": "this is excellent news",
        "summary": "fantastic result",
    })
    assert out is None


def test_score_signal_returns_none_for_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_SENTIMENT", raising=False)
    assert sentiment.score_signal({}) is None
    assert sentiment.score_signal({"evidence_quote": "  ", "summary": ""}) is None


def test_score_signal_real_path_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real vaderSentiment round-trip if the lib is available.

    Skips when vaderSentiment isn't installed (CI environments without the
    dep should still pass). When installed, asserts the obvious sentiment
    direction for a clearly positive sample.
    """
    pytest.importorskip("vaderSentiment")
    monkeypatch.delenv("MASF_SENTIMENT", raising=False)
    result = sentiment.score_signal({
        "evidence_quote": "excellent breakthrough, record-breaking achievement",
        "summary": "amazing news for the team",
    })
    assert result is not None
    score, label = result
    assert -1.0 <= score <= 1.0
    assert label in ("positive", "neutral", "negative")
    assert label == "positive"  # the sample is clearly positive
