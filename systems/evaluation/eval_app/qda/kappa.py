"""Pairwise Cohen's κ between two labels.yaml files.

Use cases (all from pre-reg §5 and the thesis backlog):

  * intra-rater κ — Anna codes the same 50 signals twice with a 7-day
    cooling-off period, then computes κ between rounds. The two YAML
    files might be `labels_round1.yaml` + `labels_round2.yaml`.

  * inter-rater κ — Supervisor double-codes 10 signals. `labels.yaml`
    (Anna) vs `labels_supervisor.yaml` on the overlapping signal_ids.

The function works on the intersection of `signal_id` between the two
files. Out-of-shape rows are skipped with a warning.

Returns κ per axis (signal_type, dimension, keep, actor_correct) plus
the count of rows compared. scikit-learn's cohen_kappa_score is used
when available; we fall back to a vendored implementation so the qda
sub-package can be tested without the heavy dep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class KappaResult:
    n_compared: int = 0
    n_skipped: int = 0
    per_axis: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def pairwise_kappa(path_a: str | Path, path_b: str | Path) -> KappaResult:
    """Compute κ on signal_type / dimension / keep / actor_correct."""
    rows_a = _load_rows(path_a)
    rows_b = _load_rows(path_b)
    by_id_a = {str(r["signal_id"]): r for r in rows_a if isinstance(r, dict) and r.get("signal_id")}
    by_id_b = {str(r["signal_id"]): r for r in rows_b if isinstance(r, dict) and r.get("signal_id")}
    shared = sorted(set(by_id_a) & set(by_id_b))

    result = KappaResult(n_compared=len(shared))
    if not shared:
        result.notes.append("no overlapping signal_ids between the two files")
        return result

    for axis, key in (
        ("signal_type", "gold_signal_type"),
        ("dimension",   "gold_dimension"),
        ("keep",        "gold_keep"),
        ("actor_correct", "gold_actor_correct"),
    ):
        pairs = []
        for sid in shared:
            va = by_id_a[sid].get(key)
            vb = by_id_b[sid].get(key)
            if va is None or vb is None:
                continue
            pairs.append((str(va), str(vb)))
        if not pairs:
            result.per_axis[axis] = {"n": 0, "kappa": None}
            continue
        a_vals = [p[0] for p in pairs]
        b_vals = [p[1] for p in pairs]
        kappa = _cohen_kappa(a_vals, b_vals)
        agreement = sum(1 for p in pairs if p[0] == p[1]) / len(pairs)
        result.per_axis[axis] = {
            "n": len(pairs),
            "kappa": round(kappa, 4) if kappa is not None else None,
            "raw_agreement": round(agreement, 4),
        }
    return result


def stratified_summary(path: str | Path) -> dict[str, Any]:
    """Quick per-cell count of a labels.yaml.

    Useful for the dashboard `/qda/status` page so Anna can see whether
    her gold set still hits the pre-reg §5 stratification target.
    """
    rows = _load_rows(path)
    by_type: dict[str, int] = {}
    by_dim: dict[str, int] = {}
    drops = 0
    actor_wrong = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        st = r.get("gold_signal_type") or "unspecified"
        dim = r.get("gold_dimension") or "unspecified"
        by_type[st] = by_type.get(st, 0) + 1
        by_dim[dim] = by_dim.get(dim, 0) + 1
        if r.get("gold_keep") is False:
            drops += 1
        if r.get("gold_actor_correct") is False:
            actor_wrong += 1
    return {
        "n_total": len(rows),
        "by_signal_type": by_type,
        "by_dimension": by_dim,
        "n_drops": drops,
        "n_actor_wrong": actor_wrong,
    }


# ---------- low-level helpers ----------


def _load_rows(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    return data if isinstance(data, list) else []


def _cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Compute Cohen's κ. Tries sklearn first, falls back to vendored.

    Returns None when both rater streams are constant (κ undefined).
    """
    try:
        from sklearn.metrics import cohen_kappa_score
        return float(cohen_kappa_score(a, b))
    except Exception:
        return _vendored_cohen_kappa(a, b)


def _vendored_cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Pure-Python Cohen's κ — same formula as sklearn (no weighting)."""
    if len(a) != len(b) or not a:
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    # Confusion matrix
    idx = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    cm = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        cm[idx[x]][idx[y]] += 1
    # Observed agreement
    po = sum(cm[i][i] for i in range(k)) / n
    # Expected agreement under independence
    row_sums = [sum(row) for row in cm]
    col_sums = [sum(cm[i][j] for i in range(k)) for j in range(k)]
    pe = sum(row_sums[i] * col_sums[i] for i in range(k)) / (n * n)
    if pe >= 1.0:
        return None
    return (po - pe) / (1.0 - pe)
