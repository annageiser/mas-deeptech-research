"""Env-driven settings for the eval harness.

Reads the same SUPABASE_URL / SUPABASE_SERVICE_KEY that the two MAS systems
use, plus a small set of EVAL_* knobs for what to evaluate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    supabase_url: str
    supabase_service_key: str
    # Evaluation window for the active comparison. Inter-system agreement +
    # token efficiency look at runs within this window. Defaults to 90 days
    # to match the v0.4.0 dashboard.
    window_days: int = 90
    # Where to write results.json + results.md
    output_dir: str = "data/eval"
    # Where to read the manually-labelled gold set from (YAML).
    # Format: see systems/evaluation/data/gold/labels.yaml.example
    gold_set_path: str = "data/gold/labels.yaml"

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)


def load_settings() -> Settings:
    return Settings(
        supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
        supabase_service_key=os.environ.get("SUPABASE_SERVICE_KEY", "").strip(),
        window_days=int(os.environ.get("EVAL_WINDOW_DAYS", "90") or "90"),
        output_dir=os.environ.get("EVAL_OUTPUT_DIR", "data/eval").rstrip("/"),
        gold_set_path=os.environ.get("EVAL_GOLD_PATH", "data/gold/labels.yaml"),
    )
