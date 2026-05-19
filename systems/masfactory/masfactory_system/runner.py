"""CLI entrypoint — invoked by cron (or by hand) inside Container A.

Usage:
    python -m masfactory_system.runner run-once [--limit-actors N] [--actors-file PATH]
    python -m masfactory_system.runner build-check          # build-time smoke
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict
from typing import Any

import yaml
from masfactory import Agent, template_defaults_for

from .audit import AuditFolder
from .config import ConfigError, load_settings
from .graph import build_graph
from .model import build_main_model
from .persistence import SupabaseStore
from .schema import Actor


DEFAULT_ACTORS_FILE = "/data/raw/actors.yaml"


def _load_actors(path: str) -> list[Actor]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return [Actor.model_validate(a) for a in raw.get("actors", [])]


def _config_snapshot(settings) -> dict[str, Any]:
    """Redacted snapshot of settings safe to write to Supabase."""
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

    store = SupabaseStore(settings)
    store.upsert_actors([a.model_dump(mode="json") for a in actors])

    audit = AuditFolder.create(settings.audit_dir)
    actor_pool = [a.model_dump(mode="json") for a in actors]

    config_snapshot = _config_snapshot(settings)
    audit.write_json("config.json", config_snapshot)
    audit.write_json("actor_pool.json", actor_pool)

    run_id = store.start_run(actor_slugs=[a.slug for a in actors], config_snapshot=config_snapshot)

    model = build_main_model(settings)
    candidate_actors_json = json.dumps(actor_pool)

    try:
        with template_defaults_for(type_filter=Agent, model=model):
            graph = build_graph()
            graph.build()
            _, attrs = graph.invoke(
                {
                    "candidate_actors_json": candidate_actors_json,
                    "limit_actors": limit_actors,
                },
                attributes={
                    "actor_pool": actor_pool,
                    "limit_actors": limit_actors,
                    "limit_arxiv_per_actor": settings.limit_arxiv_per_actor,
                    "limit_website_pages_per_actor": settings.limit_website_pages_per_actor,
                    "web_cache_dir": "/data/raw/web_cache",
                    "store": store,
                    "audit_folder": audit,
                    "run_id": run_id,
                    "config_snapshot": config_snapshot,
                    "candidate_actors_json": candidate_actors_json,
                },
            )
    except Exception as exc:
        traceback.print_exc()
        audit.write_text("error.txt", f"{type(exc).__name__}: {exc}")
        store.finish_run(run_id, status="error", error_message=str(exc)[:1000])
        return 1

    audit.write_json("final_attributes.json", _attrs_for_disk(attrs))

    store.finish_run(run_id, status="ok")
    print(
        f"run {run_id}: kept={attrs.get('signals_kept', 0)} inserted={attrs.get('signals_inserted', 0)}"
        f" audit={audit.root}"
    )
    return 0


def _attrs_for_disk(attrs: dict[str, Any]) -> dict[str, Any]:
    """Drop non-JSON-serialisable attributes before writing to disk."""
    safe: dict[str, Any] = {}
    for key, value in attrs.items():
        if key in ("store", "audit_folder"):
            continue
        try:
            json.dumps(value, default=str)
        except TypeError:
            safe[key] = repr(value)
        else:
            safe[key] = value
    return safe


class _StubModel:
    """Minimal Model stand-in used only by the build-time smoke check.

    Agent nodes require a `model` keyword at materialization, so to validate
    that the graph wiring compiles without real credentials we feed each Agent
    this stub. `invoke()` is never called during the build check.
    """

    __node_template_scope__ = "shared"

    def __init__(self) -> None:
        from masfactory.adapters.model.base import ModelCapabilities
        from masfactory.adapters.token_usage_tracker import TokenUsageTracker

        self._model_name = "stub"
        self._description = "build-check stub"
        self._client = None
        self._default_invoke_settings = None
        self._settings_mapping = {}
        self._settings_default = {}
        self._capabilities = ModelCapabilities()
        self._token_tracker = TokenUsageTracker(model_name="stub", api_key="stub", base_url=None)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def description(self) -> str:
        return self._description

    @property
    def capabilities(self):
        return self._capabilities

    @property
    def token_tracker(self):
        return self._token_tracker

    def invoke(self, *_args, **_kwargs):  # pragma: no cover — never called at build-time
        raise NotImplementedError("build-check stub: invoke() must not be called")


def cmd_build_check(_args: argparse.Namespace) -> int:
    """Build-time smoke test: graph compiles without env vars / network."""
    with template_defaults_for(type_filter=Agent, model=_StubModel()):
        graph = build_graph()
        graph.build()
    print("ok: graph compiled")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="masfactory-runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_once = sub.add_parser("run-once", help="Process a single batch and exit (used by cron).")
    run_once.add_argument("--limit-actors", type=int, default=None)
    run_once.add_argument("--actors-file", type=str, default=None)
    run_once.set_defaults(func=cmd_run_once)

    build_check = sub.add_parser("build-check", help="Compile the graph without invoking it.")
    build_check.set_defaults(func=cmd_build_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
