"""Loads the canonical classification schema (signalling-theory model) so the
Methodology endpoint cites exactly what the Classifier/Critic agents use.

The schema.yaml is copied into the image at build time from
systems/masfactory/masfactory_system/classification/schema.yaml.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import yaml

from . import labels as L
from .config import load_settings


@lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    path = load_settings().schema_path
    if not os.path.isfile(path):
        # Fallback: reconstruct a minimal schema from labels so the endpoint
        # still works if the YAML wasn't copied (e.g. local dev).
        return _schema_from_labels()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or _schema_from_labels()
    except Exception:
        return _schema_from_labels()


def _schema_from_labels() -> dict[str, Any]:
    dims = []
    for key in L.DIMENSION_LABEL:
        dims.append({
            "key": key,
            "label": L.dimension(key),
            "channel": "capability" if key in L.CAPABILITY_DIMENSIONS else "legitimacy",
            "is_technical": key in L.CAPABILITY_DIMENSIONS,
            "weight": L.DIMENSION_WEIGHT.get(key, 0.8),
            "signal_cost": L.DIMENSION_COST.get(key, "medium"),
            "observability": L.DIMENSION_OBSERVABILITY.get(key, "medium"),
            "description": L.DIMENSION_HINT.get(key, ""),
        })
    return {
        "version": "labels-fallback",
        "cost_classes": {k: {"multiplier": v} for k, v in L.COST_MULTIPLIER.items()},
        "dimensions": dims,
    }


def meta_payload() -> dict[str, Any]:
    """The full machine-readable methodology: dimensions with all three axes,
    cost classes, channels, references."""
    sc = schema()
    dims = []
    for d in sc.get("dimensions", []):
        key = d.get("key")
        dims.append({
            "key": key,
            "label": L.dimension(key),
            "channel": d.get("channel"),
            "channel_label": "Capability" if d.get("channel") == "capability" else "Legitimacy",
            "is_technical": d.get("is_technical"),
            "weight": d.get("weight"),
            "signal_cost": d.get("signal_cost"),
            "cost_label": L.COST_LABEL.get(d.get("signal_cost", "medium"), "Medium-cost"),
            "cost_multiplier": L.COST_MULTIPLIER.get(d.get("signal_cost", "medium"), 0.7),
            "observability": d.get("observability"),
            "description": d.get("description", "").strip(),
            "grounding": (d.get("grounding") or "").strip(),
        })
    return {
        "version": sc.get("version"),
        "last_revised": sc.get("last_revised"),
        "channels": sc.get("channels", []),
        "cost_classes": sc.get("cost_classes", {}),
        "signalling_theory": sc.get("signalling_theory", {}),
        "dimensions": dims,
        "category_labels": L.CATEGORY_LABEL,
        "category_colors": L.CATEGORY_COLOR,
        "system_labels": L.SYSTEM_LABEL,
        "source_kind_labels": L.SOURCE_KIND_LABEL,
    }
