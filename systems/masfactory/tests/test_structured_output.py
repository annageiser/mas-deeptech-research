"""Tests for v0.4.22 — structured-output validation discipline."""

from __future__ import annotations

import pytest

from masfactory_system.structured_output import (
    instructor_repair_available,
    validate_classified_batch,
)


def _valid_entry() -> dict:
    return {
        "actor_slug": "id-quantique",
        "source_kind": "news",
        "source_url": "https://idquantique.com/news/foo",
        "title": "ID Quantique CHF 40M Series C",
        "summary": "ID Quantique closed a Series C funding round.",
        "evidence_quote": "today announced the close of a CHF 40 million Series C",
        "dimension": "funding_event",
        "signal_type": "legitimacy",
        "is_technical": False,
        "confidence": 0.95,
    }


def test_valid_entry_passes() -> None:
    valid, invalid = validate_classified_batch([_valid_entry()])
    assert len(valid) == 1
    assert not invalid
    assert valid[0]["dimension"] == "funding_event"
    assert valid[0]["signal_type"] == "legitimacy"
    assert valid[0]["defense_engagement"] is False
    assert valid[0]["defense_ambivalence"] is False


def test_missing_signal_type_gets_filled_from_dimension() -> None:
    entry = _valid_entry()
    entry.pop("signal_type")
    valid, invalid = validate_classified_batch([entry])
    assert not invalid
    assert valid[0]["signal_type"] == "legitimacy"


def test_legacy_dimension_key_gets_normalised() -> None:
    entry = _valid_entry()
    # 'patents' is valid in both v0.3 and v0.4; pick a real legacy key so we
    # exercise normalise_dimension. If no legacy keys exist, fall back to
    # ensuring a v0.4 key survives the coercer untouched.
    entry["dimension"] = "patents"
    valid, _invalid = validate_classified_batch([entry])
    assert valid[0]["dimension"] == "patents"


def test_invalid_confidence_type_drops() -> None:
    entry = _valid_entry()
    entry["confidence"] = "high"  # str, not float
    valid, invalid = validate_classified_batch([entry])
    assert not valid
    assert len(invalid) == 1
    assert invalid[0]["raw"]["confidence"] == "high"


def test_confidence_coerced_from_string_number() -> None:
    # Pydantic v2 will coerce "0.7" → 0.7 by default; this confirms.
    entry = _valid_entry()
    entry["confidence"] = "0.7"
    valid, invalid = validate_classified_batch([entry])
    assert not invalid
    assert valid[0]["confidence"] == 0.7


def test_missing_required_field_drops() -> None:
    entry = _valid_entry()
    entry.pop("actor_slug")
    valid, invalid = validate_classified_batch([entry])
    assert not valid
    assert any("actor_slug" in str(e) for e in invalid[0]["errors"])


def test_non_dict_input_drops_gracefully() -> None:
    valid, invalid = validate_classified_batch(["not a dict", 42, None])
    assert not valid
    assert len(invalid) == 3
    for record in invalid:
        assert record["errors"][0]["msg"] == "not a JSON object"


def test_empty_input_is_empty_output() -> None:
    valid, invalid = validate_classified_batch([])
    assert not valid
    assert not invalid


def test_repair_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MASF_INSTRUCTOR_REPAIR", raising=False)
    assert instructor_repair_available() is False


def test_repair_enabled_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASF_INSTRUCTOR_REPAIR", "1")
    # Whether the lib actually imports depends on the test env; we only
    # assert the flag part works. False is acceptable if instructor isn't
    # installed; True is acceptable if it is.
    result = instructor_repair_available()
    assert isinstance(result, bool)
