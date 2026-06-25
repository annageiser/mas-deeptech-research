"""Stratified sampler — produce a .qdpx for the qualitative coder.

Sampling rule (pre-reg §5): 50 signals, stratified across
  4 actor categories × 4 signal_types
keeping ≥ 3 per cell where the corpus permits.

Sampling source:
  - public.signals filtered to the evaluation window
  - system IN (masfactory, hermes) — manual signals excluded so the
    coder's gold doesn't get contaminated with Anna's own editorial layer
  - one row per signal (we DON'T pair the systems — each row is a
    distinct (signal, system) tuple, but the coder labels the EVENT
    not the system's prediction, so we de-duplicate by content_hash
    if both systems found the same event)

The actor category comes from actors.category (one of 5 values per
data/raw/actors.yaml). The four cells per actor category × four
signal types is 16 cells; targeting ~3 per cell gets us 48 — we round
up to 50 by re-balancing populous cells.

Seed control:
  --seed N    deterministic sampler (default reads EVAL_GOLD_SEED env
              or falls back to 42).
  The selected signal_ids are written to data/gold/seed.txt at the
  same time as the .qdpx — meeting pre-reg §5 "Random seed recorded
  in data/gold/seed.txt".
"""

from __future__ import annotations

import os
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from .. import data_access as da
from .codebook import (
    DEFENSE_FLAGS,
    SIGNAL_TYPE_DISPLAY,
    build_codebook,
)
from .refi_qda import AppliedCode, SignalSource, write_qdpx


_DEFAULT_SEED = 42
_TARGET_TOTAL = 50

# Schema path — relative to repo root. Resolved at runtime so the
# eval container can either find it via /repo or /data depending on
# the bind-mount.
_DEFAULT_SCHEMA_PATHS = (
    "/repo/systems/masfactory/masfactory_system/classification/schema.yaml",
    "systems/masfactory/masfactory_system/classification/schema.yaml",
    "../masfactory/masfactory_system/classification/schema.yaml",
)


def _resolve_schema_path(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in _DEFAULT_SCHEMA_PATHS:
        if Path(candidate).is_file():
            return Path(candidate)
    raise FileNotFoundError(
        "Could not locate schema.yaml. Pass --schema explicitly. "
        f"Tried: {_DEFAULT_SCHEMA_PATHS}"
    )


@dataclass
class ExportSummary:
    out_path: Path
    seed_file: Path
    n_sources: int
    cells: dict[str, int]
    skipped_no_actor_meta: int


def export_stratified_sample(
    *,
    out_path: str | Path,
    window_days: int = 28,
    sample_size: int = _TARGET_TOTAL,
    seed: Optional[int] = None,
    schema_path: Optional[str] = None,
    seed_file: Optional[str | Path] = None,
) -> ExportSummary:
    """Build a .qdpx file for the coder + record the seed.

    Returns an `ExportSummary` describing what was written.
    """
    seed_val = (
        seed
        if seed is not None
        else int(os.environ.get("EVAL_GOLD_SEED", str(_DEFAULT_SEED)) or _DEFAULT_SEED)
    )
    rng = random.Random(seed_val)

    # Pull the two MAS-system signals from Supabase. We do NOT include
    # `system='manual'` rows: those are Anna's own editorial labels
    # and would obviously bias her own coding.
    signals_a = da.signals(system="masfactory", days=window_days)
    signals_b = da.signals(system="hermes", days=window_days)
    signals = pd.concat([signals_a, signals_b], ignore_index=True)
    if signals.empty:
        raise RuntimeError(
            f"No signals from masfactory/hermes within the last {window_days} days. "
            "Run a cron or widen the window."
        )

    actors_df = da.actors()
    actors_by_slug = {row["slug"]: row for _, row in actors_df.iterrows()}

    # Each row in `signals` carries `system`, `signal_type`, `dimension`.
    # We use the (normalised) signal_type as one stratification axis and
    # actor.category as the other.
    chosen, cell_counts, skipped = _stratified_pick(
        signals_df=signals,
        actors_by_slug=actors_by_slug,
        sample_size=sample_size,
        rng=rng,
    )
    if not chosen:
        raise RuntimeError("Stratified sampler returned zero rows — investigate corpus distribution.")

    # ---- Build sources + codebook ----
    schema = _resolve_schema_path(schema_path)
    codebook = build_codebook(schema)

    sources: list[SignalSource] = []
    for row in chosen:
        actor = actors_by_slug.get(row["actor_slug"], {})
        actor_name = (actor.get("name") if isinstance(actor, dict) else actor.get("name", row["actor_slug"]))
        text = _compose_source_text(row, actor_name=actor_name)

        # Pre-attach the system's own prediction as a coder='system_a' /
        # 'system_b' coding so the importer can recover both: gold (coder
        # 'anna') + each system's verdict. NOTE: we pre-attach the
        # system_type, dimension, and defense flags but NOT keep/actor —
        # those are Anna's call alone, not the system's.
        applied: list[AppliedCode] = []
        coder = "system_a" if row.get("system") == "masfactory" else "system_b"
        # signal_type display name
        st_display = SIGNAL_TYPE_DISPLAY.get(row.get("signal_type") or "")
        if st_display:
            applied.append(AppliedCode(code_name=st_display, coder_name=coder))
        # dimension
        if row.get("dimension"):
            applied.append(AppliedCode(code_name=str(row["dimension"]), coder_name=coder))
        # defense flags — render only when true
        for key, display, _ in DEFENSE_FLAGS:
            if bool(row.get(key, False)):
                applied.append(AppliedCode(code_name=display, coder_name=coder))

        sources.append(SignalSource(
            signal_id=str(row["id"]),
            name=f"{actor_name} | {(row.get('title') or '')[:80]}",
            text=text,
            pre_existing_codings=applied,
        ))

    out_path = Path(out_path)
    project_name = f"Swiss-quantum gold set ({window_days}-day window, seed={seed_val})"
    write_qdpx(
        out_path,
        codebook=codebook,
        sources=sources,
        project_name=project_name,
        creating_user="anna",
    )

    # Record the seed + the selected signal_ids next to the file so
    # pre-reg §5's "seed recorded" requirement is satisfied without
    # the coder having to track it manually.
    seed_path = Path(seed_file) if seed_file else out_path.with_suffix(".seed.txt")
    seed_path.write_text(
        "\n".join([
            f"# Generated by eval_app.qda.exporter",
            f"# window_days={window_days}",
            f"# sample_size={sample_size}",
            f"# seed={seed_val}",
            f"# n_sources={len(sources)}",
            "",
            *[str(s.signal_id) for s in sources],
            "",
        ]),
        encoding="utf-8",
    )

    return ExportSummary(
        out_path=out_path,
        seed_file=seed_path,
        n_sources=len(sources),
        cells=cell_counts,
        skipped_no_actor_meta=skipped,
    )


# ---------- internals ----------


def _stratified_pick(
    *,
    signals_df: pd.DataFrame,
    actors_by_slug: dict,
    sample_size: int,
    rng: random.Random,
) -> tuple[list[dict], dict[str, int], int]:
    """Stratified sample across (actor.category, signal_type) cells.

    Returns (chosen_rows, per_cell_counts, n_skipped_for_missing_actor).
    """
    # De-dup at the EVENT level (same content_hash across the two systems
    # = same event coded twice). Keep the highest-confidence representative
    # so the source text the coder sees is the better-quality one.
    if "content_hash" in signals_df.columns:
        signals_df = (signals_df.sort_values("confidence", ascending=False, na_position="last")
                                .drop_duplicates(subset=["content_hash"], keep="first")
                                .reset_index(drop=True))

    # Bucket by (category, signal_type).
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    skipped = 0
    for _, row in signals_df.iterrows():
        actor = actors_by_slug.get(row["actor_slug"])
        if actor is None:
            skipped += 1
            continue
        category = actor.get("category") if isinstance(actor, dict) else actor.get("category", "")
        signal_type = row.get("signal_type") or ""
        if not category or not signal_type:
            skipped += 1
            continue
        cells[(category, signal_type)].append(row.to_dict())

    if not cells:
        return [], {}, skipped

    # Target per cell: aim for ceil(sample_size / n_cells) but never
    # more than the cell holds.
    n_cells = len(cells)
    base_quota = max(1, sample_size // n_cells)
    chosen: list[dict] = []
    leftover_pool: list[dict] = []
    counts: dict[str, int] = {}
    for cell_key, rows in cells.items():
        rng.shuffle(rows)
        take = rows[:base_quota]
        leftover = rows[base_quota:]
        chosen.extend(take)
        leftover_pool.extend(leftover)
        counts[f"{cell_key[0]}/{cell_key[1]}"] = len(take)

    # Top up to the target sample size from the leftover pool (random).
    if len(chosen) < sample_size and leftover_pool:
        rng.shuffle(leftover_pool)
        extra = leftover_pool[: sample_size - len(chosen)]
        chosen.extend(extra)
        for row in extra:
            actor = actors_by_slug.get(row["actor_slug"], {})
            category = actor.get("category") if isinstance(actor, dict) else actor.get("category", "")
            key = f"{category}/{row.get('signal_type') or ''}"
            counts[key] = counts.get(key, 0) + 1

    rng.shuffle(chosen)  # final order is also seed-deterministic
    return chosen, counts, skipped


def _compose_source_text(row: dict, *, actor_name: str) -> str:
    """The text the coder sees inside QualCoder / ATLAS.ti per signal.

    Includes everything the coder needs to call a category WITHOUT
    leaving the QDA tool. The trailer carries the system's own
    classification so the coder can compare — but the coder should
    code the EVIDENCE, not the system's verdict.
    """
    parts: list[str] = [
        f"Actor : {actor_name} ({row.get('actor_slug') or ''})",
        f"Title : {row.get('title') or ''}",
        f"URL   : {row.get('source_url') or ''}",
        f"Kind  : {row.get('source_kind') or ''}",
        "",
        "==== Evidence quote ====",
        (row.get("evidence_quote") or "").strip() or "(none)",
        "",
        "==== Summary ====",
        (row.get("summary") or "").strip() or "(none)",
        "",
        "==== System prediction (for comparison only) ====",
        f"system          : {row.get('system') or ''}",
        f"signal_type     : {row.get('signal_type') or ''}",
        f"dimension       : {row.get('dimension') or ''}",
        f"confidence      : {row.get('confidence', 0):.2f}",
        f"defense_engage  : {bool(row.get('defense_engagement', False))}",
        f"defense_ambival : {bool(row.get('defense_ambivalence', False))}",
        "",
        "—— Coder instructions —————————————————————————",
        "Apply EXACTLY ONE signal_type code (4 categories),",
        "EXACTLY ONE dimension code (within that signal_type),",
        "0..N defense flags (only when evidence is explicit),",
        "EXACTLY ONE keep/drop AND ONE actor-attribution code.",
        "Add a memo for non-trivial calls (especially for 'Drop').",
    ]
    return "\n".join(parts)
