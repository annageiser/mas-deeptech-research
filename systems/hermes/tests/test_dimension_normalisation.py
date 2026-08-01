"""System B must classify against the same closed vocabulary as System A.

`dimension` is the shared measurement instrument, not a property of either
architecture. If one system is held to the nineteen canonical keys and the
other is told the field is free text, the classification comparison measures
the instructions rather than the systems.

That is what was happening. Until v0.5.4 the skill said `dimension` was a
"free-text sub-category" and two of its four worked examples used labels that
are not in the taxonomy. The agent complied exactly: 88 percent of System B's
July signals (1304 of 1484) carried one of 214 invented labels, against 0
percent for System A over the same period.

It also broke scoring silently. api_app/scoring.py resolves DIMENSION_WEIGHT
and DIMENSION_COST by key and falls back to 0.8 / "medium" on a miss, so the
headline metrics for System B were computed almost entirely from fallback
constants instead of the signalling-theory weights.

These tests pin three things: the vendored key list matches the canonical
schema, the skill teaches that list, and the persister backstop corrects only
what it can defend and leaves the rest visible.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import persist_signals as ps


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_YAML = (REPO_ROOT / "systems" / "masfactory" / "masfactory_system"
               / "classification" / "schema.yaml")
SKILL_MD = (REPO_ROOT / "systems" / "hermes" / "skills"
            / "collect-swiss-quantum-signals" / "SKILL.md")

_needs_repo = pytest.mark.skipif(
    not SCHEMA_YAML.is_file(),
    reason="canonical schema not reachable (running outside a repo checkout)",
)


def _canonical_dimensions() -> set[str]:
    """Parse the 19 keys out of schema.yaml.

    Regex rather than PyYAML on purpose: this package's runtime dependencies
    are httpx and selectolax, and a test should not widen them.
    """
    text = SCHEMA_YAML.read_text(encoding="utf-8")
    block = text[text.index("\ndimensions:"):]
    return set(re.findall(r"^\s*-\s*key:\s*([a-z_]+)\s*$", block, re.M))


# ---------- the vendored list must not drift from the canonical one ----------

@_needs_repo
def test_vendored_vocabulary_matches_the_canonical_schema():
    """VALID_DIMENSIONS is a hand-copied constant, because the
    comparison-validity invariant forbids importing masfactory_system. This is
    the guard that keeps the copy honest."""
    canonical = _canonical_dimensions()

    assert len(canonical) == 19, f"expected 19 canonical dimensions, parsed {len(canonical)}"
    assert ps.VALID_DIMENSIONS == canonical, (
        "vendored VALID_DIMENSIONS has drifted from schema.yaml; "
        f"missing={sorted(canonical - ps.VALID_DIMENSIONS)} "
        f"extra={sorted(ps.VALID_DIMENSIONS - canonical)}"
    )


@_needs_repo
def test_every_synonym_resolves_to_a_canonical_key():
    """A synonym pointing at a non-existent key would silently produce
    off-taxonomy rows while looking like a correction."""
    canonical = _canonical_dimensions()
    for source, target in ps.DIMENSION_SYNONYMS.items():
        assert target in canonical, f"synonym {source!r} maps to unknown key {target!r}"
        assert source not in canonical, (
            f"{source!r} is itself canonical and must not be remapped to {target!r}"
        )


# ---------- the skill must teach the vocabulary ----------

@_needs_repo
def test_skill_enumerates_all_nineteen_keys():
    """The root cause. The agent can only use the closed list if it is given
    the closed list."""
    canonical = _canonical_dimensions()
    text = SKILL_MD.read_text(encoding="utf-8")
    backticked = set(re.findall(r"`([a-z_]+)`", text))

    missing = canonical - backticked
    assert not missing, f"SKILL.md does not name these canonical dimensions: {sorted(missing)}"


@_needs_repo
def test_skill_does_not_call_the_field_free_text():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "free-text sub-category" not in text, (
        "the skill still describes `dimension` as free text, which is the "
        "instruction that produced 214 invented labels"
    )


@_needs_repo
def test_skill_worked_examples_use_valid_dimensions():
    """Two of the four examples used to teach off-taxonomy labels, and those
    exact labels then dominated the drift in production."""
    canonical = _canonical_dimensions()
    text = SKILL_MD.read_text(encoding="utf-8")
    used = set(re.findall(r"dimension=([a-z_]+)", text))

    assert used, "the skill should carry worked examples"
    invalid = used - canonical
    assert not invalid, f"skill examples teach invalid dimensions: {sorted(invalid)}"


# ---------- the persister backstop ----------

def test_canonical_values_pass_through_unflagged():
    for key in sorted(ps.VALID_DIMENSIONS):
        assert ps._normalise_dimension(key) == (key, False)


@pytest.mark.parametrize("raw,expected", [
    ("publication", "publications"),          # 275 rows in the July corpus
    ("strategic_positioning", "roadmaps"),    # 153 rows
    ("pilot_announcement", "pilots_pocs"),    # 66 rows
    ("conference_role", "educational_outreach"),   # 38 rows
    ("leadership_appointment", "leadership_expertise"),  # 31 rows
    ("certification", "regulatory_recognition"),
    ("patent", "patents"),
])
def test_observed_drift_is_corrected(raw, expected):
    """Each case is a label actually seen in the production corpus."""
    value, was_off = ps._normalise_dimension(raw)
    assert value == expected
    assert was_off is True, "a correction must still be reported as drift"


@pytest.mark.parametrize("raw", [
    "  PATENT  ", "Publication", "Strategic Positioning", "pilot-announcement",
])
def test_casing_spacing_and_hyphens_are_tolerated(raw):
    value, _ = ps._normalise_dimension(raw)
    assert value in ps.VALID_DIMENSIONS


def test_ambiguous_labels_are_left_alone_not_guessed():
    """`consortium_membership` (124 rows) could be industry_partnerships or
    academic_partnerships depending on who the partner is. Guessing would
    fabricate a classification the agent never made, so it stays as drift and
    gets counted."""
    value, was_off = ps._normalise_dimension("consortium_membership")
    assert value == "consortium_membership"
    assert was_off is True
    assert "consortium_membership" not in ps.DIMENSION_SYNONYMS


def test_unmappable_label_is_preserved_and_reported():
    value, was_off = ps._normalise_dimension("some_label_nobody_predicted")
    assert value == "some_label_nobody_predicted", "must not be coerced"
    assert was_off is True, "must be counted as drift"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_input_is_reported_rather_than_crashing(raw):
    value, was_off = ps._normalise_dimension(raw)
    assert value == ""
    assert was_off is True
