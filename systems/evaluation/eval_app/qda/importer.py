"""Read a coded REFI-QDA `.qdpx` → write `data/gold/labels.yaml`.

After Anna codes the .qdpx in QualCoder (or any REFI-QDA-compliant
tool), she runs the importer. It walks every TextSource, picks the
codings whose `creatingUser` matches `--coder` (default: 'anna'), maps
them back to (signal_type, dimension, defense flags, keep, actor) and
writes a labels.yaml in the gold-set format the existing
classification_quality metric already consumes.

Validation rules — refuse to write a row when:
  - signal_id missing
  - 0 or 2+ signal_type codes for this coder
  - 0 or 2+ dimension codes for this coder
  - dimension chosen does NOT live under the signal_type chosen
    (codebook hierarchy violation)
  - 0 or 2+ keep/drop codes
  - 0 or 2+ actor-attribution codes

Validation errors are printed and the row is skipped so partial
files still produce a usable labels.yaml — useful when Anna is
mid-coding and wants to compute κ on what she's already finished.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .codebook import (
    DEFENSE_FLAGS,
    QUALITY_FLAGS,
    SIGNAL_TYPE_DISPLAY,
    defense_flag_from_display,
    quality_flag_from_display,
    signal_type_from_display,
)
from .refi_qda import read_qdpx


# Build reverse maps for quick lookup at import time.
_DEFENSE_DISPLAYS = {display: key for key, display, _ in DEFENSE_FLAGS}
_QUALITY_DISPLAYS = {display: key for key, display, _ in QUALITY_FLAGS}
_SIGNAL_TYPE_DISPLAYS = {display: key for key, display in SIGNAL_TYPE_DISPLAY.items()}


@dataclass
class ImportSummary:
    out_path: Path
    n_sources_seen: int
    n_rows_written: int
    n_skipped: int
    coder: str
    errors: list[str]


def import_coded_package(
    qdpx_path: str | Path,
    *,
    out_path: str | Path,
    coder: str = "anna",
    merge_with_existing: bool = True,
) -> ImportSummary:
    """Convert a coded .qdpx into a gold-set YAML file.

    If `merge_with_existing` is True (default) and `out_path` exists,
    rows are merged on `signal_id` — Anna can re-code a subset and
    re-import without losing earlier rows. Existing rows for the same
    signal_id get OVERWRITTEN with the new coding.
    """
    qdpx_path = Path(qdpx_path)
    out_path = Path(out_path)

    code_book, coded_sources = read_qdpx(qdpx_path)

    # Walk the codebook to figure out which signal_type each dimension
    # belongs under so we can validate hierarchy at import time.
    dimension_to_signal_type: dict[str, str] = {}
    for top in code_book.codes:
        signal_type_key = _SIGNAL_TYPE_DISPLAYS.get(top.name)
        if not signal_type_key:
            continue
        for child in top.children:
            # Dimension names are the v0.4.0 dimension keys verbatim
            # (see codebook.build_codebook).
            dimension_to_signal_type[child.name] = signal_type_key

    new_rows: list[dict] = []
    errors: list[str] = []
    skipped = 0
    today = _dt.date.today().isoformat()

    for src in coded_sources:
        applied = src.codings.get(coder) or []
        if not applied:
            skipped += 1
            errors.append(f"{src.signal_id}: no codings for coder={coder!r}")
            continue

        row, err = _build_gold_row(
            signal_id=src.signal_id,
            applied_codes=applied,
            dimension_to_signal_type=dimension_to_signal_type,
            coder=coder,
            labelled_at=today,
        )
        if err is not None:
            skipped += 1
            errors.append(f"{src.signal_id}: {err}")
            continue
        new_rows.append(row)

    # Optionally merge with existing rows.
    final_rows = _merge_rows(out_path, new_rows) if merge_with_existing else new_rows

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(final_rows, sort_keys=False, allow_unicode=True), encoding="utf-8")

    return ImportSummary(
        out_path=out_path,
        n_sources_seen=len(coded_sources),
        n_rows_written=len(new_rows),
        n_skipped=skipped,
        coder=coder,
        errors=errors,
    )


# ---------- helpers ----------


def _build_gold_row(
    *,
    signal_id: str,
    applied_codes: list[str],
    dimension_to_signal_type: dict[str, str],
    coder: str,
    labelled_at: str,
) -> tuple[dict, Optional[str]]:
    """Validate the per-source code set and produce one gold row.

    Returns (row, None) on success, (empty_dict, error_message) on failure.
    """
    signal_types: list[str] = []
    dimensions: list[str] = []
    defense_engagement = False
    defense_ambivalence = False
    keep_decision: Optional[bool] = None
    actor_correct: Optional[bool] = None

    for name in applied_codes:
        # Signal type?
        st_key = signal_type_from_display(name) or _SIGNAL_TYPE_DISPLAYS.get(name)
        if st_key:
            signal_types.append(st_key)
            continue
        # Defense flag?
        df_key = defense_flag_from_display(name) or _DEFENSE_DISPLAYS.get(name)
        if df_key == "defense_engagement":
            defense_engagement = True
            continue
        if df_key == "defense_ambivalence":
            defense_ambivalence = True
            continue
        # Quality flag?
        qf_key = quality_flag_from_display(name) or _QUALITY_DISPLAYS.get(name)
        if qf_key == "gold_keep_true":
            if keep_decision is not None:
                return {}, "two keep/drop codes applied — pick exactly one"
            keep_decision = True
            continue
        if qf_key == "gold_keep_false":
            if keep_decision is not None:
                return {}, "two keep/drop codes applied — pick exactly one"
            keep_decision = False
            continue
        if qf_key == "gold_actor_correct":
            if actor_correct is not None:
                return {}, "two actor-attribution codes applied — pick exactly one"
            actor_correct = True
            continue
        if qf_key == "gold_actor_wrong":
            if actor_correct is not None:
                return {}, "two actor-attribution codes applied — pick exactly one"
            actor_correct = False
            continue
        # Otherwise it's a dimension (or an unknown code we just skip).
        if name in dimension_to_signal_type:
            dimensions.append(name)

    if len(signal_types) != 1:
        return {}, f"need exactly 1 signal_type code, got {len(signal_types)}: {signal_types!r}"
    if len(dimensions) != 1:
        return {}, f"need exactly 1 dimension code, got {len(dimensions)}: {dimensions!r}"
    expected_parent = dimension_to_signal_type.get(dimensions[0])
    if expected_parent != signal_types[0]:
        return {}, (
            f"dimension {dimensions[0]!r} belongs to signal_type "
            f"{expected_parent!r}, but coder picked {signal_types[0]!r}"
        )
    if keep_decision is None:
        return {}, "missing keep/drop code"
    if actor_correct is None:
        return {}, "missing actor-attribution code"

    return {
        "signal_id": signal_id,
        "gold_signal_type": signal_types[0],
        "gold_dimension": dimensions[0],
        "gold_keep": bool(keep_decision),
        "gold_actor_correct": bool(actor_correct),
        # Defense flags surfaced even though the existing
        # classification_quality metric does not yet score them —
        # forward-compat for the calibration A/B (backlog item P2 #23).
        "gold_defense_engagement": defense_engagement,
        "gold_defense_ambivalence": defense_ambivalence,
        "labelled_by": coder,
        "labelled_at": labelled_at,
    }, None


def _merge_rows(out_path: Path, new_rows: list[dict]) -> list[dict]:
    """If `out_path` exists, merge new_rows over the existing rows on signal_id.

    New rows REPLACE existing rows of the same signal_id; rows in the
    existing file that aren't in new_rows are kept untouched. This
    lets Anna re-code a subset (e.g. supervisor's 10 rows) and append
    without re-coding the whole file.
    """
    if not out_path.is_file():
        return new_rows
    try:
        existing = yaml.safe_load(out_path.read_text(encoding="utf-8")) or []
    except Exception:
        return new_rows
    if not isinstance(existing, list):
        return new_rows

    by_id: dict[str, dict] = {}
    for row in existing:
        if isinstance(row, dict) and row.get("signal_id"):
            by_id[str(row["signal_id"])] = row
    for row in new_rows:
        by_id[str(row["signal_id"])] = row
    # Stable order: original file order first, then any newly-appended.
    seen: set[str] = set()
    out: list[dict] = []
    for row in existing:
        if isinstance(row, dict):
            sid = str(row.get("signal_id") or "")
            if sid in by_id and sid not in seen:
                out.append(by_id[sid])
                seen.add(sid)
    for row in new_rows:
        sid = str(row["signal_id"])
        if sid not in seen:
            out.append(by_id[sid])
            seen.add(sid)
    return out
