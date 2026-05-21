"""CLI for the reports container."""

from __future__ import annotations

import argparse
import sys
import traceback

from .config import ConfigError, load_settings


def cmd_daily(args: argparse.Namespace) -> int:
    from .daily import generate_daily

    settings = load_settings(require_supabase=True)
    out = generate_daily(settings=settings, system=args.system)
    print(f"daily report written: {out['path']}")
    print(f"  signals_count={out['snapshot_summary']['signal_count']} runs={out['snapshot_summary']['run_count']}")
    print(f"  tokens in={out['tokens']['input']} out={out['tokens']['output']} calls={out['tokens']['calls']}")
    return 0


def cmd_weekly(args: argparse.Namespace) -> int:
    from .weekly_system import generate_weekly_system

    settings = load_settings(require_supabase=True)
    out = generate_weekly_system(settings=settings, system=args.system)
    print(f"weekly report written: {out['path']}")
    print(
        f"  this_week signals={out['this_week_summary']['signal_count']}"
        f" prev_week signals={out['previous_week_summary']['signal_count']}"
    )
    print(f"  tokens in={out['tokens']['input']} out={out['tokens']['output']} calls={out['tokens']['calls']}")
    return 0


def cmd_weekly_thesis(_args: argparse.Namespace) -> int:
    from .weekly_thesis import generate_weekly_thesis

    settings = load_settings(require_supabase=True)
    out = generate_weekly_thesis(settings=settings)
    print(f"weekly thesis report written: {out['path']}")
    print(f"  commits_in_window={out['commit_count']}")
    print(f"  tokens in={out['tokens']['input']} out={out['tokens']['output']} calls={out['tokens']['calls']}")
    return 0


def cmd_build_check(_args: argparse.Namespace) -> int:
    """Build-time smoke: imports + prompt loading work without network."""
    from .prompt_loader import load_prompt

    for name in ("daily", "weekly_system", "weekly_thesis"):
        snippet = load_prompt(name)[:80].replace("\n", " ")
        print(f"prompt {name}.md ok ({len(snippet)} chars shown): {snippet}…")
    print("ok: reports_system imports + prompts load")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reports-runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_daily = sub.add_parser("daily", help="Write a daily report for one system.")
    p_daily.add_argument("--system", choices=("masfactory", "hermes"), required=True)
    p_daily.set_defaults(func=cmd_daily)

    p_weekly = sub.add_parser("weekly", help="Write a weekly report for one system.")
    p_weekly.add_argument("--system", choices=("masfactory", "hermes"), required=True)
    p_weekly.set_defaults(func=cmd_weekly)

    p_thesis = sub.add_parser("weekly-thesis", help="Write the weekly thesis-progress report.")
    p_thesis.set_defaults(func=cmd_weekly_thesis)

    p_build = sub.add_parser("build-check", help="Verify imports + prompts (no network).")
    p_build.set_defaults(func=cmd_build_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 3
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
