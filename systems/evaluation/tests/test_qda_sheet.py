"""Spreadsheet route to a gold set: export blinding, import validation.

Hermetic — data_access is monkeypatched, no Supabase.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest
import yaml

from eval_app.qda import sheet as sh


SCHEMA = (Path(__file__).resolve().parents[3] / "systems" / "masfactory"
          / "masfactory_system" / "classification" / "schema.yaml")

pytestmark = pytest.mark.skipif(
    not SCHEMA.is_file(), reason="canonical schema not reachable outside a checkout"
)


def _signals(n=24) -> pd.DataFrame:
    cats = ["private_company", "university_or_research_hub"]
    types = ["legitimacy", "customer_cocreation", "community_ecosystem", "future_trajectory"]
    rows = []
    for i in range(n):
        rows.append({
            "id": f"11111111-0000-0000-0000-{i:012d}",
            "actor_slug": f"a{i % 2}",
            "system": "hermes" if i % 2 else "masfactory",
            "signal_type": types[i % 4],
            "dimension": "funding_event",
            "title": f"Signal {i}",
            "summary": f"summary {i}",
            "evidence_quote": f"quote {i}",
            "source_url": f"https://example.invalid/{i}",
            "source_kind": "news",
            "confidence": 0.5 + (i % 5) / 10,
            "content_hash": f"h{i}",
            "inserted_at": "2026-07-15T00:00:00+00:00",
        })
    return pd.DataFrame(rows)


@pytest.fixture
def fake_corpus(monkeypatch):
    actors = pd.DataFrame([
        {"slug": "a0", "name": "Actor Zero", "category": "private_company"},
        {"slug": "a1", "name": "Actor One", "category": "university_or_research_hub"},
    ])
    sig = _signals()
    monkeypatch.setattr(sh.da, "actors", lambda: actors)
    monkeypatch.setattr(
        sh.da, "signals",
        lambda system=None, days=90: sig[sig["system"] == system] if system else sig,
    )
    return sig


def _read(path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------- export ----------

def test_sheet_is_blind_to_the_producing_system(tmp_path, fake_corpus):
    """A coder who can see the machine's answer ratifies it. The sheet must
    carry neither the system nor its labels, or every agreement statistic is
    inflated."""
    out = tmp_path / "g.csv"
    sh.export_sheet(out_path=out, sample_size=12, schema_path=str(SCHEMA))

    header = _read(out)[0].keys()
    for leak in ("system", "signal_type", "dimension", "confidence"):
        assert leak not in header, f"the sheet leaks {leak!r} to the coder"
    assert "gold_signal_type" in header and "gold_dimension" in header


def test_sheet_carries_enough_context_to_judge(tmp_path, fake_corpus):
    out = tmp_path / "g.csv"
    sh.export_sheet(out_path=out, sample_size=12, schema_path=str(SCHEMA))
    row = _read(out)[0]
    for needed in ("signal_id", "actor", "title", "evidence_quote", "source_url"):
        assert row[needed], f"{needed} is empty; the coder cannot judge without it"


def test_gold_columns_start_empty(tmp_path, fake_corpus):
    out = tmp_path / "g.csv"
    sh.export_sheet(out_path=out, sample_size=12, schema_path=str(SCHEMA))
    for row in _read(out):
        for col in sh.GOLD_COLUMNS:
            assert row[col] == ""


def test_export_is_seed_deterministic(tmp_path, fake_corpus):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    sh.export_sheet(out_path=a, sample_size=12, seed=7, schema_path=str(SCHEMA))
    sh.export_sheet(out_path=b, sample_size=12, seed=7, schema_path=str(SCHEMA))
    assert a.read_text() == b.read_text(), "same seed must give the same sample"


def test_howto_lists_every_allowed_value(tmp_path, fake_corpus):
    out = tmp_path / "g.csv"
    sh.export_sheet(out_path=out, sample_size=12, schema_path=str(SCHEMA))
    guide = (tmp_path / "g.HOWTO.txt").read_text()
    for st in sh.SIGNAL_TYPES:
        assert st in guide
    for dim in sh.valid_dimensions(str(SCHEMA)):
        assert dim in guide, f"HOWTO omits {dim}"


def test_empty_corpus_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(sh.da, "signals", lambda system=None, days=90: pd.DataFrame())
    monkeypatch.setattr(sh.da, "actors", lambda: pd.DataFrame())
    with pytest.raises(RuntimeError, match="No masfactory/hermes signals"):
        sh.export_sheet(out_path=tmp_path / "g.csv", schema_path=str(SCHEMA))


# ---------- import ----------

def _sheet(tmp_path, rows) -> Path:
    p = tmp_path / "filled.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sh.CONTEXT_COLUMNS + sh.GOLD_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in sh.CONTEXT_COLUMNS + sh.GOLD_COLUMNS}, **r})
    return p


def test_import_writes_labels_the_metric_can_read(tmp_path):
    src = _sheet(tmp_path, [{
        "signal_id": "s1", "gold_keep": "true", "gold_signal_type": "legitimacy",
        "gold_dimension": "funding_event", "gold_actor_correct": "true",
        "notes": "clear grant announcement",
    }])
    out = tmp_path / "labels.yaml"
    s = sh.import_sheet(src, out_path=out, schema_path=str(SCHEMA))

    assert s.n_labelled == 1 and not s.errors
    entry = yaml.safe_load(out.read_text())[0]
    assert entry["signal_id"] == "s1"
    assert entry["gold_signal_type"] == "legitimacy"
    assert entry["gold_dimension"] == "funding_event"
    assert entry["gold_keep"] is True
    assert entry["labelled_by"] == "anna" and entry["labelled_at"]


@pytest.mark.parametrize("yes", ["true", "TRUE", "Yes", "y", "1", "ja"])
def test_boolean_spellings_a_human_actually_types(tmp_path, yes):
    src = _sheet(tmp_path, [{
        "signal_id": "s1", "gold_keep": yes, "gold_signal_type": "legitimacy",
        "gold_dimension": "funding_event", "gold_actor_correct": yes,
    }])
    s = sh.import_sheet(src, out_path=tmp_path / "l.yaml", schema_path=str(SCHEMA))
    assert s.n_labelled == 1, f"{yes!r} should parse as true"


def test_rejected_signal_needs_no_category_labels(tmp_path):
    """Forcing a signal_type onto something the coder just said is noise would
    fabricate a classification of a row that should not exist."""
    src = _sheet(tmp_path, [{
        "signal_id": "s1", "gold_keep": "false", "gold_actor_correct": "true",
        "notes": "boilerplate, no dated event",
    }])
    out = tmp_path / "l.yaml"
    s = sh.import_sheet(src, out_path=out, schema_path=str(SCHEMA))

    assert s.n_labelled == 1 and not s.errors
    entry = yaml.safe_load(out.read_text())[0]
    assert entry["gold_keep"] is False
    assert "gold_signal_type" not in entry


def test_invalid_dimension_is_rejected_with_a_useful_message(tmp_path):
    src = _sheet(tmp_path, [{
        "signal_id": "s1", "gold_keep": "true", "gold_signal_type": "legitimacy",
        "gold_dimension": "publication", "gold_actor_correct": "true",
    }])
    s = sh.import_sheet(src, out_path=tmp_path / "l.yaml", schema_path=str(SCHEMA))

    assert s.n_labelled == 0
    assert any("publication" in e and "canonical" in e for e in s.errors)


def test_invalid_signal_type_is_rejected(tmp_path):
    src = _sheet(tmp_path, [{
        "signal_id": "s1", "gold_keep": "true", "gold_signal_type": "legitimcy",
        "gold_dimension": "funding_event", "gold_actor_correct": "true",
    }])
    s = sh.import_sheet(src, out_path=tmp_path / "l.yaml", schema_path=str(SCHEMA))
    assert s.n_labelled == 0 and any("legitimcy" in e for e in s.errors)


def test_untouched_rows_are_counted_not_errors(tmp_path):
    src = _sheet(tmp_path, [
        {"signal_id": "s1", "gold_keep": "true", "gold_signal_type": "legitimacy",
         "gold_dimension": "funding_event", "gold_actor_correct": "true"},
        {"signal_id": "s2"},
        {"signal_id": "s3"},
    ])
    s = sh.import_sheet(src, out_path=tmp_path / "l.yaml", schema_path=str(SCHEMA))
    assert (s.n_labelled, s.n_blank, s.errors) == (1, 2, [])


def test_partially_filled_row_is_an_error_not_a_silent_drop(tmp_path):
    src = _sheet(tmp_path, [{"signal_id": "s1", "gold_signal_type": "legitimacy"}])
    s = sh.import_sheet(src, out_path=tmp_path / "l.yaml", schema_path=str(SCHEMA))
    assert s.n_labelled == 0
    assert any("gold_keep is required" in e for e in s.errors)


def test_reimport_merges_on_signal_id(tmp_path):
    out = tmp_path / "l.yaml"
    first = _sheet(tmp_path, [{
        "signal_id": "s1", "gold_keep": "true", "gold_signal_type": "legitimacy",
        "gold_dimension": "funding_event", "gold_actor_correct": "true"}])
    sh.import_sheet(first, out_path=out, schema_path=str(SCHEMA))

    second = tmp_path / "second.csv"
    with second.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sh.CONTEXT_COLUMNS + sh.GOLD_COLUMNS)
        w.writeheader()
        base = {c: "" for c in sh.CONTEXT_COLUMNS + sh.GOLD_COLUMNS}
        w.writerow({**base, "signal_id": "s2", "gold_keep": "true",
                    "gold_signal_type": "roadmaps" and "future_trajectory",
                    "gold_dimension": "roadmaps", "gold_actor_correct": "true"})
    sh.import_sheet(second, out_path=out, schema_path=str(SCHEMA))

    ids = {e["signal_id"] for e in yaml.safe_load(out.read_text())}
    assert ids == {"s1", "s2"}, "a second batch must not clobber the first"


def test_bad_boolean_is_reported(tmp_path):
    src = _sheet(tmp_path, [{"signal_id": "s1", "gold_keep": "maybe"}])
    s = sh.import_sheet(src, out_path=tmp_path / "l.yaml", schema_path=str(SCHEMA))
    assert any("not true/false" in e for e in s.errors)


def test_round_trip_export_then_import(tmp_path, fake_corpus):
    """The whole loop: export, fill every row, import, and the ids must line up."""
    csv_path = tmp_path / "g.csv"
    sh.export_sheet(out_path=csv_path, sample_size=8, schema_path=str(SCHEMA))

    rows = _read(csv_path)
    for r in rows:
        r["gold_keep"] = "true"
        r["gold_signal_type"] = "legitimacy"
        r["gold_dimension"] = "funding_event"
        r["gold_actor_correct"] = "true"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sh.CONTEXT_COLUMNS + sh.GOLD_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    out = tmp_path / "labels.yaml"
    s = sh.import_sheet(csv_path, out_path=out, schema_path=str(SCHEMA))

    assert s.n_labelled == len(rows) and not s.errors
    gold_ids = {e["signal_id"] for e in yaml.safe_load(out.read_text())}
    assert gold_ids == {r["signal_id"] for r in rows}
