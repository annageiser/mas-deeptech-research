"""Spreadsheet route to a gold set, for coders without QDA software.

`exporter.py` produces a REFI-QDA `.qdpx` for ATLAS.ti or QualCoder. That is
the right artefact for a full qualitative-coding workflow, but it needs the
software installed and learned. This module is the low-ceremony alternative:
the SAME pre-registered stratified sample (§5) written to a CSV that opens in
Excel, Numbers or Sheets, plus an importer that turns the filled sheet back
into `data/gold/labels.yaml`.

The documented manual alternative was "open /signals, pick 50, copy each UUID
by hand". That is error-prone and slow, and a mistyped UUID silently drops a
row from the metric.

BLIND BY CONSTRUCTION
---------------------
The exported sheet deliberately does NOT contain the producing system, nor the
system's own signal_type / dimension / confidence. A coder who can see the
machine's answer tends to ratify it, which inflates every agreement statistic
and makes precision look better than it is. Withholding it costs nothing --
`signal_id` recovers the system at import time -- and it is the difference
between a gold set that measures the systems and one that measures the coder's
willingness to agree.

Rows are shuffled with the same seed as the sample, so the ordering carries no
system cue either.

USAGE
-----
    python -m eval_app.qda sheet --out gold-sheet.csv --sample-size 50
    # fill in the five gold_* columns in a spreadsheet, save as CSV
    python -m eval_app.qda sheet-import gold-sheet.csv --out data/gold/labels.yaml
    python -m eval_app.runner cls
"""

from __future__ import annotations

import csv
import os
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml

from .. import data_access as da
from .exporter import _DEFAULT_SEED, _TARGET_TOTAL, _resolve_schema_path, _stratified_pick


# Columns the coder reads. No system, no machine label -- see the module
# docstring on blinding.
CONTEXT_COLUMNS = [
    "signal_id",
    "actor",
    "actor_category",
    "title",
    "summary",
    "evidence_quote",
    "source_url",
    "source_kind",
    "observed_at",
]

# Columns the coder fills.
GOLD_COLUMNS = [
    "gold_keep",
    "gold_signal_type",
    "gold_dimension",
    "gold_actor_correct",
    "notes",
]

SIGNAL_TYPES = [
    "legitimacy", "customer_cocreation", "community_ecosystem", "future_trajectory",
]

_TRUE = {"true", "yes", "y", "1", "t", "ja"}
_FALSE = {"false", "no", "n", "0", "f", "nein"}


@dataclass
class SheetSummary:
    path: str
    n_rows: int
    seed: int
    cell_counts: dict[str, int] = field(default_factory=dict)
    skipped: int = 0


@dataclass
class ImportSummary:
    path: str
    n_labelled: int
    n_blank: int
    n_rows: int
    errors: list[str] = field(default_factory=list)
    per_system: dict[str, int] = field(default_factory=dict)


def valid_dimensions(schema_path: Optional[str] = None) -> list[str]:
    with open(_resolve_schema_path(schema_path), "r", encoding="utf-8") as fh:
        schema = yaml.safe_load(fh) or {}
    return [d["key"] for d in schema.get("dimensions", [])]


# ---------------------------------------------------------------- export ----

def export_sheet(
    *,
    out_path: str | Path,
    window_days: int = 90,
    sample_size: int = _TARGET_TOTAL,
    seed: Optional[int] = None,
    schema_path: Optional[str] = None,
    balance_systems: bool = True,
) -> SheetSummary:
    """Write the stratified sample to a coder-fillable CSV.

    `balance_systems` (default on) draws half the quota from each producer
    so per-system precision has comparable support on both sides.
    """
    seed_val = (
        seed if seed is not None
        else int(os.environ.get("EVAL_GOLD_SEED", str(_DEFAULT_SEED)) or _DEFAULT_SEED)
    )
    rng = random.Random(seed_val)

    # system='manual' is excluded: those rows are the coder's own editorial
    # labels and coding them would be marking her own homework.
    per_system = {s: da.signals(system=s, days=window_days) for s in ("masfactory", "hermes")}
    if all(df.empty for df in per_system.values()):
        raise RuntimeError(
            f"No masfactory/hermes signals in the last {window_days} days. "
            "Widen --window-days or run a cron first."
        )

    actors_df = da.actors()
    actors_by_slug = {row["slug"]: row for _, row in actors_df.iterrows()}

    if balance_systems:
        # Sample each producer to its own half-quota. The corpus is lopsided
        # (2214 hermes rows against 1008 masfactory at the time of writing) and
        # the cross-system content_hash de-duplication inside _stratified_pick
        # keeps the highest-confidence representative, so a single pooled draw
        # skews hard toward the larger producer -- an early run of this came
        # back 35 hermes / 15 masfactory. Per-system precision is the whole
        # point of the gold set, and 15 labelled rows will not carry it.
        half = max(1, sample_size // 2)
        chosen, cell_counts, skipped = [], {}, 0
        for name, df in per_system.items():
            if df.empty:
                continue
            picked, counts, skip = _stratified_pick(
                signals_df=df, actors_by_slug=actors_by_slug,
                sample_size=half, rng=rng,
            )
            chosen.extend(picked)
            skipped += skip
            for cell, n in counts.items():
                cell_counts[f"{name} | {cell}"] = n
        rng.shuffle(chosen)  # order must not encode the producer
    else:
        signals = pd.concat(per_system.values(), ignore_index=True)
        chosen, cell_counts, skipped = _stratified_pick(
            signals_df=signals, actors_by_slug=actors_by_slug,
            sample_size=sample_size, rng=rng,
        )

    if not chosen:
        raise RuntimeError("Stratified sampler returned zero rows — check the corpus distribution.")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CONTEXT_COLUMNS + GOLD_COLUMNS)
        for row in chosen:
            actor = actors_by_slug.get(row["actor_slug"], {})
            actor_name = actor.get("name") if isinstance(actor, dict) else actor.get("name", "")
            category = actor.get("category") if isinstance(actor, dict) else actor.get("category", "")
            writer.writerow([
                row.get("id", ""),
                actor_name or row.get("actor_slug", ""),
                category or "",
                (row.get("title") or "").strip(),
                (row.get("summary") or "").strip(),
                (row.get("evidence_quote") or "").strip(),
                row.get("source_url") or "",
                row.get("source_kind") or "",
                (row.get("observed_at") or row.get("inserted_at") or ""),
                # gold columns start empty
                "", "", "", "", "",
            ])

    _write_instructions(out, schema_path)
    return SheetSummary(str(out), len(chosen), seed_val, cell_counts, skipped)


def _write_instructions(sheet_path: Path, schema_path: Optional[str]) -> None:
    """A short README next to the sheet, with the allowed values."""
    dims = valid_dimensions(schema_path)
    guide = sheet_path.with_suffix(".HOWTO.txt")
    guide.write_text(
        "HOW TO FILL THIS SHEET\n"
        "======================\n\n"
        f"Open {sheet_path.name} in Excel, Numbers or Google Sheets.\n"
        "Fill the five right-hand columns for every row, then save as CSV\n"
        "(keep the same column headers) and run:\n\n"
        f"    python -m eval_app.qda sheet-import {sheet_path.name} \\\n"
        "        --out data/gold/labels.yaml\n\n"
        "You are the reference standard here. Judge each signal only from the\n"
        "title, summary, evidence quote and source URL in front of you. The\n"
        "sheet deliberately does not tell you which system found the signal or\n"
        "how it labelled it, so that your labels measure the systems rather\n"
        "than your agreement with them. Open the URL if the quote is unclear.\n\n"
        "COLUMNS\n"
        "-------\n"
        "gold_keep           true / false\n"
        "                    Is this a real, dated, actor-relevant quantum\n"
        "                    signal that belongs in the corpus at all?\n"
        "                    false = noise, boilerplate, wrong topic, undated.\n"
        "                    If false, leave the two label columns blank.\n\n"
        "gold_signal_type    one of:\n"
        + "".join(f"                      {s}\n" for s in SIGNAL_TYPES) +
        "\ngold_dimension      one of the nineteen:\n"
        + "".join(f"                      {d}\n" for d in dims) +
        "\ngold_actor_correct  true / false\n"
        "                    Is the signal really about the named actor?\n"
        "                    false = it is about someone else.\n\n"
        "notes               free text, optional. Worth a line whenever the\n"
        "                    call was close — that is the material for the\n"
        "                    limitations section.\n\n"
        "PACING\n"
        "------\n"
        "Budget about two minutes per row. Do not agonise: your first\n"
        "defensible reading is the one to record. If a row is genuinely\n"
        "ambiguous, pick the closest label and say why in notes.\n\n"
        "SECOND CODER\n"
        "------------\n"
        "For an inter-rater reliability figure, have a second person label\n"
        "10-15 of the same rows in a fresh copy, import it to a different\n"
        "path, then:\n\n"
        "    python -m eval_app.qda compare data/gold/labels.yaml other.yaml\n\n"
        "That reports Cohen's kappa, which is the statistic to quote.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------- import ----

def _parse_bool(raw: str, *, field_name: str, row_no: int, errors: list[str]) -> Optional[bool]:
    v = (raw or "").strip().lower()
    if not v:
        return None
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    errors.append(f"row {row_no}: {field_name}={raw!r} is not true/false")
    return None


def import_sheet(
    csv_path: str | Path,
    *,
    out_path: str | Path,
    coder: str = "anna",
    schema_path: Optional[str] = None,
    merge: bool = True,
) -> ImportSummary:
    """Turn a filled sheet into labels.yaml, validating as it goes."""
    dims = set(valid_dimensions(schema_path))
    errors: list[str] = []
    labelled: list[dict[str, Any]] = []
    n_rows = 0
    n_blank = 0

    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as fh:
        for row_no, row in enumerate(csv.DictReader(fh), start=2):
            n_rows += 1
            sid = (row.get("signal_id") or "").strip()
            if not sid:
                errors.append(f"row {row_no}: missing signal_id")
                continue

            keep = _parse_bool(row.get("gold_keep", ""), field_name="gold_keep",
                               row_no=row_no, errors=errors)
            st = (row.get("gold_signal_type") or "").strip().lower()
            dim = (row.get("gold_dimension") or "").strip().lower()
            actor_ok = _parse_bool(row.get("gold_actor_correct", ""),
                                   field_name="gold_actor_correct",
                                   row_no=row_no, errors=errors)

            if keep is None and not st and not dim and actor_ok is None:
                n_blank += 1
                continue

            if keep is None:
                errors.append(f"row {row_no}: gold_keep is required once a row is started")
                continue

            entry: dict[str, Any] = {
                "signal_id": sid,
                "gold_keep": keep,
                "gold_actor_correct": True if actor_ok is None else actor_ok,
                "labelled_by": coder,
                "labelled_at": date.today().isoformat(),
            }

            # A rejected signal needs no category labels — asking for them
            # would force a classification of something that should not exist.
            if keep:
                if st not in SIGNAL_TYPES:
                    errors.append(
                        f"row {row_no}: gold_signal_type={st!r} is not one of {SIGNAL_TYPES}"
                    )
                    continue
                if dim not in dims:
                    errors.append(
                        f"row {row_no}: gold_dimension={dim!r} is not one of the "
                        f"{len(dims)} canonical dimensions"
                    )
                    continue
                entry["gold_signal_type"] = st
                entry["gold_dimension"] = dim

            note = (row.get("notes") or "").strip()
            if note:
                entry["notes"] = note
            labelled.append(entry)

    out = Path(out_path)
    existing: list[dict[str, Any]] = []
    if merge and out.is_file():
        existing = yaml.safe_load(out.read_text(encoding="utf-8")) or []

    by_id = {e["signal_id"]: e for e in existing}
    by_id.update({e["signal_id"]: e for e in labelled})
    merged = list(by_id.values())

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# Gold set — generated by `python -m eval_app.qda sheet-import`.\n"
        "# Hand edits are preserved: re-importing merges on signal_id.\n\n"
        + yaml.safe_dump(merged, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    return ImportSummary(
        path=str(out), n_labelled=len(labelled), n_blank=n_blank,
        n_rows=n_rows, errors=errors,
    )
