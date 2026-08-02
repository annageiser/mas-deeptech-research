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


def _cmd_sheet(args) -> int:
    from .sheet import export_sheet

    summary = export_sheet(
        out_path=args.out, window_days=args.window_days,
        sample_size=args.sample_size, seed=args.seed, schema_path=args.schema,
    )
    print(f"wrote {summary.path}  ({summary.n_rows} rows, seed={summary.seed})")
    print(f"wrote {summary.path.rsplit('.', 1)[0]}.HOWTO.txt  — read this first")
    if summary.skipped:
        print(f"  skipped {summary.skipped} rows with no resolvable actor or signal_type")
    print("  stratified cells (actor category / signal type):")
    for cell, n in sorted(summary.cell_counts.items()):
        print(f"    {n:3d}  {cell}")
    print()
    print("  Fill the five gold_* columns, save as CSV, then:")
    print(f"    python -m eval_app.qda sheet-import {summary.path} --out data/gold/labels.yaml")
    return 0


def _cmd_sheet_import(args) -> int:
    from .sheet import import_sheet

    summary = import_sheet(
        args.csv, out_path=args.out, coder=args.coder,
        schema_path=args.schema, merge=not args.no_merge,
    )
    print(f"read {summary.n_rows} rows: {summary.n_labelled} labelled, {summary.n_blank} still blank")
    print(f"wrote {summary.path}")
    if summary.errors:
        print(f"\n  {len(summary.errors)} row(s) rejected — fix and re-import:")
        for e in summary.errors[:25]:
            print(f"    {e}")
        if len(summary.errors) > 25:
            print(f"    ... and {len(summary.errors) - 25} more")
    if summary.n_blank:
        print(f"\n  {summary.n_blank} rows are still unlabelled. The metric uses what is there,")
        print("  but the pre-registered target is 50.")
    return 1 if summary.errors else 0


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

    # ---- sheet (spreadsheet route to a gold set) ----
    p_sheet = sub.add_parser(
        "sheet", help="sample signals -> coder-fillable CSV (no QDA software needed)")
    p_sheet.add_argument("--out", required=True, help="output .csv path")
    p_sheet.add_argument("--window-days", type=int, default=90,
                         help="window for the source signals (default 90)")
    p_sheet.add_argument("--sample-size", type=int, default=50,
                         help="target sample size (default 50, pre-reg §5)")
    p_sheet.add_argument("--seed", type=int, default=None,
                         help="random seed (default 42 or $EVAL_GOLD_SEED)")
    p_sheet.add_argument("--schema", default=None, help="explicit path to schema.yaml")
    p_sheet.set_defaults(func=_cmd_sheet)

    # ---- sheet-import ----
    p_si = sub.add_parser("sheet-import", help="filled CSV -> labels.yaml")
    p_si.add_argument("csv", help="the filled .csv")
    p_si.add_argument("--out", required=True, help="output labels.yaml")
    p_si.add_argument("--coder", default="anna")
    p_si.add_argument("--schema", default=None, help="explicit path to schema.yaml")
    p_si.add_argument("--no-merge", action="store_true",
                      help="overwrite labels.yaml instead of merging on signal_id")
    p_si.set_defaults(func=_cmd_sheet_import)

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
