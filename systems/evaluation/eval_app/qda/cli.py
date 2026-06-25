"""CLI for the qualitative-research workflow.

Three sub-commands:

  export    sample stratified signals from Supabase → produce a .qdpx
            ready to open in QualCoder (or ATLAS.ti / NVivo / MAXQDA /
            OpenQDA — anything REFI-QDA compliant).

  import    read a coded .qdpx → write data/gold/labels.yaml.

  compare   pairwise Cohen's κ between two labels.yaml files.
            Use for intra-rater (round 1 vs round 2) and inter-rater
            (Anna vs supervisor) κ.

Run from the repo root or inside the eval container:

    docker compose run --rm reports python -m eval_app.qda export \\
        --out data/gold/2026-07-20.qdpx --window-days 28
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .exporter import export_stratified_sample
from .importer import import_coded_package
from .kappa import pairwise_kappa, stratified_summary


def _cmd_export(args: argparse.Namespace) -> int:
    summary = export_stratified_sample(
        out_path=args.out,
        window_days=args.window_days,
        sample_size=args.sample_size,
        seed=args.seed,
        schema_path=args.schema,
        seed_file=args.seed_file,
    )
    print(f"[qda export] wrote {summary.out_path}  (n={summary.n_sources}, "
          f"seed-log {summary.seed_file})")
    print(f"[qda export] per-cell counts:")
    for cell, n in sorted(summary.cells.items()):
        print(f"    {cell:>50}  {n}")
    if summary.skipped_no_actor_meta:
        print(f"[qda export] WARN: skipped {summary.skipped_no_actor_meta} signals "
              "with missing actor metadata / signal_type")
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    summary = import_coded_package(
        qdpx_path=args.qdpx,
        out_path=args.out,
        coder=args.coder,
        merge_with_existing=not args.no_merge,
    )
    print(f"[qda import] {summary.n_rows_written}/{summary.n_sources_seen} rows "
          f"written to {summary.out_path} (coder={summary.coder!r})")
    if summary.n_skipped:
        print(f"[qda import] skipped {summary.n_skipped} rows:")
        for err in summary.errors:
            print(f"    {err}")
    if args.show_summary:
        sm = stratified_summary(summary.out_path)
        print(f"[qda import] stratified summary:")
        print(json.dumps(sm, indent=2, sort_keys=True))
    return 0 if summary.n_rows_written > 0 else 1


def _cmd_compare(args: argparse.Namespace) -> int:
    result = pairwise_kappa(args.path_a, args.path_b)
    out = {
        "n_compared": result.n_compared,
        "per_axis": result.per_axis,
        "notes": result.notes,
    }
    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(f"[qda compare] {result.n_compared} signals shared between "
              f"{Path(args.path_a).name} and {Path(args.path_b).name}")
        for axis, payload in result.per_axis.items():
            n = payload.get("n", 0)
            k = payload.get("kappa")
            agree = payload.get("raw_agreement")
            k_str = "n/a" if k is None else f"{k:.4f}"
            a_str = "n/a" if agree is None else f"{agree:.4f}"
            print(f"    {axis:>16}  n={n:>3}  κ={k_str}  agreement={a_str}")
        for note in result.notes:
            print(f"    note: {note}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    sm = stratified_summary(args.path)
    if args.json:
        print(json.dumps(sm, indent=2, sort_keys=True))
    else:
        print(f"[qda status] {args.path}: n={sm['n_total']}")
        print("  by signal_type:")
        for k, v in sorted(sm["by_signal_type"].items()):
            print(f"    {k:>20}  {v}")
        print(f"  drops={sm['n_drops']}  actor_wrong={sm['n_actor_wrong']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eval_app.qda",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ---- export ----
    p_exp = sub.add_parser("export", help="sample signals → .qdpx")
    p_exp.add_argument("--out", required=True, help="output .qdpx path")
    p_exp.add_argument("--window-days", type=int, default=28,
                       help="window for the source signals (default 28)")
    p_exp.add_argument("--sample-size", type=int, default=50,
                       help="target sample size (default 50, pre-reg §5)")
    p_exp.add_argument("--seed", type=int, default=None,
                       help="random seed (default 42 or $EVAL_GOLD_SEED)")
    p_exp.add_argument("--schema", default=None,
                       help="explicit path to schema.yaml")
    p_exp.add_argument("--seed-file", default=None,
                       help="where to write the seed.txt (default: <out>.seed.txt)")
    p_exp.set_defaults(func=_cmd_export)

    # ---- import ----
    p_imp = sub.add_parser("import", help="coded .qdpx → labels.yaml")
    p_imp.add_argument("qdpx", help="coded .qdpx path")
    p_imp.add_argument("--out", required=True, help="output labels.yaml")
    p_imp.add_argument("--coder", default="anna",
                       help="which coder's codings to read (default 'anna')")
    p_imp.add_argument("--no-merge", action="store_true",
                       help="overwrite labels.yaml instead of merging on signal_id")
    p_imp.add_argument("--show-summary", action="store_true")
    p_imp.set_defaults(func=_cmd_import)

    # ---- compare ----
    p_cmp = sub.add_parser("compare", help="pairwise Cohen's κ on two labels.yaml")
    p_cmp.add_argument("path_a")
    p_cmp.add_argument("path_b")
    p_cmp.add_argument("--json", action="store_true")
    p_cmp.set_defaults(func=_cmd_compare)

    # ---- status ----
    p_st = sub.add_parser("status", help="show stratified-cell counts for a labels.yaml")
    p_st.add_argument("path")
    p_st.add_argument("--json", action="store_true")
    p_st.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


# Allow `python -m eval_app.qda …` directly.
if __name__ == "__main__":
    raise SystemExit(main())
