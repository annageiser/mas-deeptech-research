"""Tests for the embedding gate + signal-text composition.

Does NOT load the real fastembed model — that costs 7s + 210MB on first call,
which is wrong for a unit test (and unavailable in many CI / build-check
environments). The actual embedding round-trip is smoke-tested at deploy
time via the runner's `--limit-actors 2 --embeddings` flag, not here.
"""

from __future__ import annotations

import pytest

from masfactory_system import embedding


def test_embeddings_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_EMBEDDINGS", raising=False)
    assert embedding.is_enabled() is False
    assert embedding.embed_text("any text") is None


def test_embeddings_env_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("1", "true", "yes", "on", "TRUE", "  1  "):
        monkeypatch.setenv("MASF_EMBEDDINGS", value)
        assert embedding.is_enabled() is True, f"failed for value={value!r}"


def test_embeddings_env_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ("", "0", "false", "no", "off", "anything-else"):
        monkeypatch.setenv("MASF_EMBEDDINGS", value)
        assert embedding.is_enabled() is False, f"failed for value={value!r}"


def test_embed_text_returns_none_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_EMBEDDINGS", raising=False)
    assert embedding.embed_text("Swiss Quantum Initiative announces funding") is None


def test_embed_text_returns_none_for_empty_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_EMBEDDINGS", "1")
    assert embedding.embed_text("") is None
    assert embedding.embed_text("   \n\t  ") is None


def test_compose_signal_text_includes_key_fields() -> None:
    signal = {
        "title": "SQI announces CHF 50M funding round",
        "evidence_quote": "The Swiss Quantum Initiative said it had closed a CHF 50M Series B...",
        "summary": "First major Swiss-quantum private-investor round of 2026.",
        "dimension": "funding_or_grant",
    }
    text = embedding.compose_signal_text(signal)
    assert "SQI announces CHF 50M funding round" in text
    assert "Swiss Quantum Initiative said it" in text
    assert "First major Swiss-quantum" in text
    assert "dimension:funding_or_grant" in text


def test_compose_signal_text_handles_missing_fields() -> None:
    # All fields missing → only the dimension marker survives
    text = embedding.compose_signal_text({})
    assert "dimension:unknown" in text
    assert text.strip() == "dimension:unknown"

    # Some fields present
    text = embedding.compose_signal_text({"title": "X", "dimension": "hiring_or_talent"})
    assert "X" in text
    assert "dimension:hiring_or_talent" in text


def test_model_dim_matches_schema_column() -> None:
    """If this assertion ever fires, the schema's `vector(768)` column was
    changed or the model was swapped. The two must stay in sync."""
    assert embedding.MODEL_DIM == 768


def test_embed_text_returns_none_if_fastembed_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If fastembed is somehow missing at runtime (e.g. install-time failure
    on a fresh VPS), embed_text must degrade silently to None — not crash."""
    monkeypatch.setenv("MASF_EMBEDDINGS", "1")
    # Reset the cached singleton + simulate import failure
    monkeypatch.setattr(embedding, "_model", None)

    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("simulated: fastembed not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert embedding.embed_text("any") is None
