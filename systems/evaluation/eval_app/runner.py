"""CLI entry: ``python -m eval_app.runner all``.

Computes all four metrics + writes ``results.json`` + ``results.md`` to
``$EVAL_OUTPUT_DIR/<UTC-iso>/`` (default ``data/eval/<iso>/``).

Sub-commands:
  - ``all``  — run all four metrics
  - ``isa``  — inter-system agreement only
  - ``tok``  — token efficiency only
  - ``rep``  — reproducibility only
  - ``cls``  — classification quality vs gold only
  - ``dump`` — dump the raw Supabase frames as parquet (debug)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from . import data_access as da
from .config import load_settings
from .found_sets import load_all_found_sets, summarise as summarise_found_sets
from .metrics import (
    classification_quality,
    inter_system_agreement,
    reproducibility,
    reproducibility_from_found_sets,
    token_efficiency,
)
from .report import write_results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bachelor-thesis evaluation harness")
    parser.add_argument(
        "command",
        choices=["all", "isa", "tok", "rep", "cls", "dump"],
        nargs="?",
        default="all",
        help="Which metric(s) to compute (default: all).",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=None,
        help="Override EVAL_WINDOW_DAYS for this run.",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.window_days is not None:
        settings.window_days = args.window_days

    if not settings.has_supabase:
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY missing in env", file=sys.stderr)
        return 2

    print(f"[eval] window_days={settings.window_days}, gold_path={settings.gold_set_path}")

    # Pull once, share frames across metrics.
    signals_df = da.signals(days=settings.window_days)
    runs_df = da.runs(days=settings.window_days)
    tokens_df = da.token_usage(days=settings.window_days)
    print(f"[eval] fetched: signals={len(signals_df)}, runs={len(runs_df)}, token_rows={len(tokens_df)}")

    results: dict = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "window_days": settings.window_days,
            "gold_set_path": settings.gold_set_path,
            "n_signals": len(signals_df),
            "n_runs": len(runs_df),
            "n_token_rows": len(tokens_df),
        },
    }

    if args.command in ("all", "isa"):
        results["inter_system_agreement"] = inter_system_agreement(signals_df)
    if args.command in ("all", "tok"):
        results["token_efficiency"] = token_efficiency(signals_df, tokens_df)
    if args.command in ("all", "rep"):
        # The database-derived figure. Retained for continuity, but it compares
        # what each run INSERTED, and the unique key means a re-run that
        # rediscovers the same URL inserts nothing -- so consecutive runs are
        # near-disjoint by construction. Reported as a diagnostic, not as the
        # reproducibility result.
        results["reproducibility_inserted_sets"] = reproducibility(runs_df, signals_df)

        # The real figure: what each run FOUND, read from the run artefacts.
        found = load_all_found_sets()
        print(f"[eval] found-set artefacts: {summarise_found_sets(found)}")
        if found:
            results["reproducibility"] = reproducibility_from_found_sets(found)
        else:
            results["reproducibility"] = {
                "metric": "reproducibility_from_found_sets",
                "status": "no_artefacts",
                "note": (
                    "No run artefacts reachable. Point EVAL_MASF_AUDIT_DIR at "
                    "data/raw/runs and EVAL_HERMES_RUNS_DIR at the hermes state "
                    "volume's state/runs. Without them reproducibility cannot be "
                    "measured, because the database records insertions rather "
                    "than findings."
                ),
            }
    if args.command in ("all", "cls"):
        results["classification_quality"] = classification_quality(
            signals_df, settings.gold_set_path
        )
    if args.command == "dump":
        out = os.path.join(settings.output_dir, "_dump")
        os.makedirs(out, exist_ok=True)
        signals_df.to_parquet(os.path.join(out, "signals.parquet"))
        runs_df.to_parquet(os.path.join(out, "runs.parquet"))
        tokens_df.to_parquet(os.path.join(out, "tokens.parquet"))
        print(f"[eval] dumped frames to {out}")
        return 0

    paths = write_results(results, output_dir=settings.output_dir)
    print(f"[eval] wrote {paths['md_path']}")
    print(f"[eval] wrote {paths['json_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
