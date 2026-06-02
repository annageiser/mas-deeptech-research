"""Classification quality vs a hand-labelled gold set.

Computes per-system precision / recall / F1 / accuracy on the
``dimension`` and ``signal_type`` axes, plus Cohen's κ for inter-rater-
style agreement between the system label and the gold label.

The gold set lives in ``data/gold/labels.yaml`` with shape::

    - signal_id: <uuid>          # from signals.id
      gold_signal_type: ...      # one of the 4 Ehrenthal categories
      gold_dimension: ...        # one of the 19 sub-categories
      gold_keep: true | false    # was the signal worth keeping at all?
      gold_actor_correct: true | false
      labelled_by: anna
      labelled_at: 2026-06-09

If the gold set isn't present, this metric returns a structured "no data
yet" marker so the runner can still produce a valid results.json.

scikit-learn is the only non-trivial dep; vendored installs of pandas
already pull it in transitively but we declare it explicitly in pyproject.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import yaml


def classification_quality(signals_df: pd.DataFrame, gold_path: str) -> dict[str, Any]:
    """Compute classification metrics against the YAML gold set.

    Returns a structured dict even when the gold set is missing — the
    thesis-ready markdown writer in ``report.py`` handles the "not yet"
    case by printing a clear "gold set pending" line."""
    if not os.path.isfile(gold_path):
        return {
            "metric": "classification_quality",
            "status": "no_gold_set",
            "gold_path": gold_path,
            "note": (
                "No gold set present at the configured path. Create "
                f"{gold_path} from data/gold/labels.yaml.example, "
                "label ≥ 50 signals across the 4 actor categories × 4 "
                "signal types (≥ 3 per cell where possible), and re-run."
            ),
        }

    with open(gold_path, "r", encoding="utf-8") as fh:
        gold_rows = yaml.safe_load(fh) or []
    if not gold_rows:
        return {
            "metric": "classification_quality",
            "status": "empty_gold_set",
            "gold_path": gold_path,
            "n_gold": 0,
        }

    gold = pd.DataFrame(gold_rows)
    if "signal_id" not in gold.columns:
        return {
            "metric": "classification_quality",
            "status": "malformed_gold_set",
            "note": "Each gold row needs a signal_id field.",
        }

    if signals_df.empty:
        return {
            "metric": "classification_quality",
            "status": "no_signals_in_window",
            "n_gold": int(len(gold)),
        }

    joined = signals_df.merge(gold, left_on="id", right_on="signal_id", how="inner")
    if joined.empty:
        return {
            "metric": "classification_quality",
            "status": "no_overlap",
            "n_gold": int(len(gold)),
            "note": (
                "None of the gold-labelled signal_ids are in the current "
                "evaluation window. Either re-label fresher signals, or "
                "widen EVAL_WINDOW_DAYS."
            ),
        }

    out: dict[str, Any] = {
        "metric": "classification_quality",
        "status": "ok",
        "gold_path": gold_path,
        "n_gold": int(len(gold)),
        "n_matched": int(len(joined)),
        "per_system": {},
        "ecosystem_overall": {},
    }

    # We compute three sub-metrics; each is a separate try/except so a
    # missing column in the gold doesn't sink the whole report.
    out["ecosystem_overall"]["signal_type"] = _classification_block(
        joined, "signal_type", "gold_signal_type"
    )
    out["ecosystem_overall"]["dimension"] = _classification_block(
        joined, "dimension", "gold_dimension"
    )
    out["ecosystem_overall"]["keep_decision"] = _classification_block(
        joined.assign(_kept=joined["confidence"].fillna(0) >= 0.45),  # current Critic threshold
        "_kept", "gold_keep",
    )

    # Per-system breakdown.
    for system in ("masfactory", "hermes"):
        sub = joined[joined["system"] == system]
        if sub.empty:
            out["per_system"][system] = {"n": 0}
            continue
        out["per_system"][system] = {
            "n": int(len(sub)),
            "signal_type": _classification_block(sub, "signal_type", "gold_signal_type"),
            "dimension":   _classification_block(sub, "dimension",   "gold_dimension"),
        }

    return out


def _classification_block(df: pd.DataFrame, pred_col: str, gold_col: str) -> dict[str, Any]:
    """Per-axis precision/recall/F1/accuracy + Cohen κ."""
    if pred_col not in df.columns or gold_col not in df.columns:
        return {"n": int(len(df)), "available": False, "note": f"missing {pred_col!r} or {gold_col!r}"}
    sub = df[[pred_col, gold_col]].dropna()
    if sub.empty:
        return {"n": 0, "available": False}
    try:
        from sklearn.metrics import (
            accuracy_score, cohen_kappa_score, f1_score, precision_score, recall_score,
        )
    except ImportError:
        return {"n": int(len(sub)), "available": False, "note": "scikit-learn not installed"}

    y_pred = sub[pred_col].astype(str).tolist()
    y_gold = sub[gold_col].astype(str).tolist()
    return {
        "n": int(len(sub)),
        "available": True,
        "accuracy": round(accuracy_score(y_gold, y_pred), 4),
        "precision_macro": round(precision_score(y_gold, y_pred, average="macro", zero_division=0), 4),
        "recall_macro": round(recall_score(y_gold, y_pred, average="macro", zero_division=0), 4),
        "f1_macro": round(f1_score(y_gold, y_pred, average="macro", zero_division=0), 4),
        "cohen_kappa": round(cohen_kappa_score(y_gold, y_pred), 4),
    }
