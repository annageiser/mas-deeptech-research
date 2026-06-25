"""Round-trip test: export → mutate (simulate coder) → import.

Verifies that a labels.yaml produced through the QualCoder workflow
matches what we would have written if the same codes had been applied
programmatically. Without this test, the codebook ↔ XML ↔ YAML chain
is too long to keep correct under future edits.

Does not require Supabase — we build SignalSource objects directly
and bypass the stratified sampler.
"""

from __future__ import annotations

import tempfile
import uuid
import zipfile
from pathlib import Path

import pytest
import yaml

from eval_app.qda.codebook import build_codebook
from eval_app.qda.importer import import_coded_package
from eval_app.qda.kappa import pairwise_kappa
from eval_app.qda.refi_qda import AppliedCode, SignalSource, read_qdpx, write_qdpx


# Resolve schema.yaml relative to repo root from inside the tests/ dir.
_SCHEMA = Path(__file__).resolve().parents[2] / "masfactory" / "masfactory_system" / "classification" / "schema.yaml"


@pytest.fixture
def codebook():
    return build_codebook(_SCHEMA)


@pytest.fixture
def sample_signals():
    """Three synthetic signals to round-trip."""
    return [
        ("00000000-0000-0000-0000-000000000001", "Anna's source 1",
         "Body 1 — Swiss Quantum Call 2026 announcement."),
        ("00000000-0000-0000-0000-000000000002", "Anna's source 2",
         "Body 2 — ETH/IBM partnership press release."),
        ("00000000-0000-0000-0000-000000000003", "Anna's source 3",
         "Body 3 — DARPA contract win at IDQ."),
    ]


def _make_sources(triples):
    return [
        SignalSource(signal_id=sid, name=name, text=text)
        for sid, name, text in triples
    ]


def _apply_anna_codings(sources, codings_by_id):
    """Inject 'anna' codings into each source the way QualCoder would."""
    for src in sources:
        applied = [AppliedCode(code_name=name, coder_name="anna")
                   for name in codings_by_id.get(src.signal_id, [])]
        src.pre_existing_codings = applied
    return sources


def test_round_trip_minimal(tmp_path, codebook, sample_signals):
    """A 3-signal round trip with valid coder selections produces a
    labels.yaml the classification_quality metric can read."""
    sources = _apply_anna_codings(_make_sources(sample_signals), {
        sample_signals[0][0]: [
            "Legitimacy", "funding_event",
            "Keep — worth keeping", "Actor attribution correct",
        ],
        sample_signals[1][0]: [
            "Community ecosystem", "industry_partnerships",
            "Keep — worth keeping", "Actor attribution correct",
        ],
        sample_signals[2][0]: [
            "Customer co-creation", "collaborations_applications",
            "Defense engagement",  # adds the flag
            "Keep — worth keeping", "Actor attribution correct",
        ],
    })

    qdpx_path = tmp_path / "round.qdpx"
    write_qdpx(qdpx_path, codebook=codebook, sources=sources,
               project_name="round-trip test", creating_user="anna")

    # Sanity: it's a real zip with project.qde + 3 source files.
    with zipfile.ZipFile(qdpx_path) as zf:
        names = set(zf.namelist())
    assert "project.qde" in names
    assert len([n for n in names if n.startswith("sources/")]) == 3

    # Re-read codebook + codings.
    _, coded = read_qdpx(qdpx_path)
    assert len(coded) == 3
    by_id = {c.signal_id: c for c in coded}
    for src_id, _, _ in sample_signals:
        assert "anna" in by_id[src_id].codings

    # Import into labels.yaml.
    labels_path = tmp_path / "labels.yaml"
    summary = import_coded_package(qdpx_path, out_path=labels_path, coder="anna")
    assert summary.n_rows_written == 3
    assert summary.n_skipped == 0
    rows = yaml.safe_load(labels_path.read_text())
    by_id = {r["signal_id"]: r for r in rows}

    r1 = by_id[sample_signals[0][0]]
    assert r1["gold_signal_type"] == "legitimacy"
    assert r1["gold_dimension"] == "funding_event"
    assert r1["gold_keep"] is True
    assert r1["gold_actor_correct"] is True

    r3 = by_id[sample_signals[2][0]]
    assert r3["gold_defense_engagement"] is True
    assert r3["gold_defense_ambivalence"] is False


def test_validation_catches_two_signal_types(tmp_path, codebook, sample_signals):
    """Two signal_type codes for the same source → row skipped."""
    sources = _apply_anna_codings(_make_sources(sample_signals[:1]), {
        sample_signals[0][0]: [
            "Legitimacy", "Customer co-creation",  # invalid: 2 signal_types
            "funding_event", "Keep — worth keeping",
            "Actor attribution correct",
        ],
    })
    qdpx_path = tmp_path / "bad.qdpx"
    write_qdpx(qdpx_path, codebook=codebook, sources=sources,
               project_name="bad", creating_user="anna")
    labels_path = tmp_path / "labels.yaml"
    summary = import_coded_package(qdpx_path, out_path=labels_path, coder="anna")
    assert summary.n_rows_written == 0
    assert summary.n_skipped == 1
    assert any("signal_type" in e for e in summary.errors)


def test_validation_catches_hierarchy_violation(tmp_path, codebook, sample_signals):
    """`funding_event` belongs to Legitimacy, not Future trajectory."""
    sources = _apply_anna_codings(_make_sources(sample_signals[:1]), {
        sample_signals[0][0]: [
            "Future trajectory", "funding_event",   # mismatch
            "Keep — worth keeping", "Actor attribution correct",
        ],
    })
    qdpx_path = tmp_path / "hier.qdpx"
    write_qdpx(qdpx_path, codebook=codebook, sources=sources,
               project_name="hier", creating_user="anna")
    labels_path = tmp_path / "labels.yaml"
    summary = import_coded_package(qdpx_path, out_path=labels_path, coder="anna")
    assert summary.n_rows_written == 0
    assert summary.n_skipped == 1
    assert any("belongs to signal_type" in e for e in summary.errors)


def test_multi_coder_filter(tmp_path, codebook, sample_signals):
    """Both Anna and supervisor code the same source — importer
    extracts only the requested coder's codings."""
    sources = _make_sources(sample_signals[:2])
    sources[0].pre_existing_codings = [
        AppliedCode("Legitimacy", "anna"),
        AppliedCode("funding_event", "anna"),
        AppliedCode("Keep — worth keeping", "anna"),
        AppliedCode("Actor attribution correct", "anna"),
        # Supervisor disagrees on dimension
        AppliedCode("Legitimacy", "supervisor"),
        AppliedCode("awards", "supervisor"),
        AppliedCode("Keep — worth keeping", "supervisor"),
        AppliedCode("Actor attribution correct", "supervisor"),
    ]
    sources[1].pre_existing_codings = [
        AppliedCode("Community ecosystem", "anna"),
        AppliedCode("industry_partnerships", "anna"),
        AppliedCode("Keep — worth keeping", "anna"),
        AppliedCode("Actor attribution correct", "anna"),
        AppliedCode("Community ecosystem", "supervisor"),
        AppliedCode("industry_partnerships", "supervisor"),
        AppliedCode("Keep — worth keeping", "supervisor"),
        AppliedCode("Actor attribution correct", "supervisor"),
    ]

    qdpx_path = tmp_path / "multi.qdpx"
    write_qdpx(qdpx_path, codebook=codebook, sources=sources,
               project_name="multi", creating_user="anna")

    labels_anna = tmp_path / "labels_anna.yaml"
    labels_supervisor = tmp_path / "labels_supervisor.yaml"
    s_anna = import_coded_package(qdpx_path, out_path=labels_anna, coder="anna")
    s_super = import_coded_package(qdpx_path, out_path=labels_supervisor, coder="supervisor")
    assert s_anna.n_rows_written == 2
    assert s_super.n_rows_written == 2

    # Inter-rater κ on dimension axis: 1/2 disagreement on r1.
    result = pairwise_kappa(labels_anna, labels_supervisor)
    assert result.n_compared == 2
    assert result.per_axis["signal_type"]["raw_agreement"] == 1.0
    assert result.per_axis["dimension"]["raw_agreement"] == 0.5
