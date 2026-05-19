"""System B CLI entry point.

Usage:
    python -m hermes_system.runner run-once [--limit-actors N] [--actors-file PATH] [--skills SLUGS]
    python -m hermes_system.runner build-check
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict
from typing import Any

import yaml

from .agent import AIAgent
from .audit import AuditFolder
from .config import ConfigError, load_settings
from .memory import MemoryManager
from .persistence import SupabaseStore
from .providers import OpenRouterProvider
from .skills_loader import SkillsLoader


DEFAULT_ACTORS_FILE = "/data/raw/actors.yaml"


def _load_actors(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return list(raw.get("actors", []))


def _config_snapshot(settings) -> dict[str, Any]:
    snap = asdict(settings)
    for secret in ("openrouter_api_key", "supabase_service_key"):
        if snap.get(secret):
            snap[secret] = f"<redacted len={len(snap[secret])}>"
    return snap


def cmd_run_once(args: argparse.Namespace) -> int:
    settings = load_settings(require_supabase=True)
    actors_file = args.actors_file or DEFAULT_ACTORS_FILE
    actors = _load_actors(actors_file)
    if not actors:
        print(f"no actors in {actors_file}", file=sys.stderr)
        return 2

    limit_actors = args.limit_actors or settings.limit_actors
    actors = actors[:limit_actors]

    store = SupabaseStore(settings)
    store.upsert_actors(actors)
    audit = AuditFolder.create(settings.audit_dir)

    config_snapshot = _config_snapshot(settings)
    audit.write_json("config.json", config_snapshot)
    audit.write_json("actor_pool.json", actors)

    run_id = store.start_run(
        actor_slugs=[a["slug"] for a in actors],
        config_snapshot=config_snapshot,
    )

    provider = OpenRouterProvider(settings)
    memory = MemoryManager(settings.memory_path)
    loader = SkillsLoader(settings.skills_dir)
    skill_names = (args.skills.split(",") if args.skills else None)
    agent = AIAgent(
        settings=settings,
        provider=provider,
        skills_loader=loader,
        memory=memory,
        skill_names=skill_names,
    )

    total_signals = 0
    briefs: list[str] = []

    try:
        for actor in actors:
            row_id = memory.log_run_start(run_id, actor["slug"])
            result = agent.run_actor(actor)
            audit.write_json(f"actor_{actor['slug']}.json", {
                "iterations_used": result.iterations_used,
                "stopped_reason": result.stopped_reason,
                "signals_count": len(result.signals),
                "transcript": result.transcript,
            })
            rows = store.derive_signal_rows(run_id, result.signals)
            inserted = store.insert_signals(rows)
            total_signals += inserted
            memory.log_run_finish(row_id, inserted, result.brief_md)
            if result.brief_md:
                briefs.append(f"## {actor['slug']}\n\n{result.brief_md}")
    except Exception as exc:
        traceback.print_exc()
        audit.write_text("error.txt", f"{type(exc).__name__}: {exc}")
        store.finish_run(run_id, status="error", error_message=str(exc)[:1000])
        return 1

    audit.write_text("brief.md", "\n\n---\n\n".join(briefs) if briefs else "(no briefs)")
    audit.write_json(
        "tokens.json",
        {
            "total_input_tokens": provider.tally.input_tokens,
            "total_output_tokens": provider.tally.output_tokens,
            "calls": provider.tally.calls,
            "per_model": provider.tally.per_model,
        },
    )
    # Mirror to Supabase token_usage so cross-system queries are easy.
    store.record_token_usage(
        run_id,
        [
            {"node_name": "ai_agent", "model_name": model, **counts}
            for model, counts in provider.tally.per_model.items()
        ],
    )
    store.finish_run(run_id, status="ok")
    print(
        f"run {run_id}: actors={len(actors)} signals_inserted={total_signals}"
        f" audit={audit.root}"
    )
    return 0


def cmd_build_check(_args: argparse.Namespace) -> int:
    """Build-time smoke test: package imports cleanly, skill files parse."""
    from .skills_loader import SkillsLoader
    import os

    # Discover skills relative to the package install location so the check
    # works inside the Docker build where /app/skills is mounted.
    skills_dir = os.environ.get("HRM_SKILLS_DIR", "/app/skills")
    loaded = SkillsLoader(skills_dir).discover()
    print(f"ok: hermes_system imports; skills_dir={skills_dir} skills={[s.name for s in loaded]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_once = sub.add_parser("run-once", help="Process a single batch and exit (used by cron).")
    run_once.add_argument("--limit-actors", type=int, default=None)
    run_once.add_argument("--actors-file", type=str, default=None)
    run_once.add_argument("--skills", type=str, default=None,
                          help="Comma-separated skill names; omit to load all.")
    run_once.set_defaults(func=cmd_run_once)

    build_check = sub.add_parser("build-check", help="Verify imports and skill files (no network).")
    build_check.set_defaults(func=cmd_build_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
