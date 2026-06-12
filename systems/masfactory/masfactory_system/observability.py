"""v0.4.25 — Phoenix observability for replayable LLM-call traces (task #125).

Why this exists
---------------
MASFactory's audit folder captures inputs/outputs per run as JSON. That's
enough to *re-read* what happened but not enough to *replay* it: there's
no LLM-call boundary, no timing breakdown, no tool-call tree, no easy way
to spot a node that kept retrying for 90s. Phoenix (Arize's open-source
LLM tracing platform) fills that gap.

When enabled, every Chat Completions call the OpenAI SDK makes is wrapped
as an OpenTelemetry span and shipped to the Phoenix server. The Phoenix
UI then shows:
  - per-run timeline + total tokens
  - which node sent which prompt
  - response latency + token cost per call
  - errors + retries + failover invocations

This is gold for the thesis evaluation chapter — "how does the consensus
critic's debate pattern compare cost-wise to the single-pass critic"
becomes a 30-second comparison in the UI rather than an audit-folder
spelunking exercise.

How it plugs in
---------------
- Phoenix runs as its own docker-compose service (`phoenix`).
- This module's `init()` is called once at runner startup.
- The OpenInference auto-instrumentor patches the openai SDK at import
  time; no manual span wrapping needed at the agent layer.
- Heavily defensive: any import failure (missing deps in dev env, no
  network to Phoenix collector) is a logged warning, not a crash.

Gating
------
  PHOENIX_ENABLED=1                   turn the tracer on (off by default)
  PHOENIX_COLLECTOR_ENDPOINT          default http://phoenix:6006
  PHOENIX_PROJECT_NAME                default masfactory-swiss-quantum

Off-by-default because:
  - Adds a small fixed overhead per LLM call.
  - Requires the phoenix service to be running (compose-up).
  - The thesis evaluation chapter cares about a few representative runs,
    not every cron tick going back forever.
"""

from __future__ import annotations

import logging
import os
from threading import Lock

log = logging.getLogger(__name__)


DEFAULT_ENDPOINT = "http://phoenix:6006"
DEFAULT_PROJECT = "masfactory-swiss-quantum"


_initialized = False
_init_lock = Lock()


def is_enabled() -> bool:
    """Off by default. Turn on with PHOENIX_ENABLED=1|true|yes|on."""
    return os.environ.get("PHOENIX_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on"
    )


def collector_endpoint() -> str:
    return (os.environ.get("PHOENIX_COLLECTOR_ENDPOINT") or DEFAULT_ENDPOINT).strip()


def project_name() -> str:
    return (os.environ.get("PHOENIX_PROJECT_NAME") or DEFAULT_PROJECT).strip()


def init(run_id: str | None = None) -> bool:
    """Initialise Phoenix tracing once per process.

    Returns:
      - True  if instrumentation activated successfully (or was already on).
      - False if Phoenix is disabled OR deps missing OR the collector
        registration failed. Caller's pipeline runs normally either way.

    `run_id`, when provided, is attached as a resource attribute so the
    Phoenix UI can group all spans from this cron tick together.
    """
    global _initialized
    if not is_enabled():
        return False
    with _init_lock:
        if _initialized:
            return True
        endpoint = collector_endpoint()
        project = project_name()
        try:
            # phoenix.otel.register handles the OTel SDK wiring + OTLP exporter
            # against the Phoenix collector.
            from phoenix.otel import register
        except ImportError:
            log.warning(
                "phoenix tracing requested but `arize-phoenix-otel` not "
                "installed — skipping. Add `arize-phoenix-otel` + "
                "`openinference-instrumentation-openai` to pyproject.toml."
            )
            return False
        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor
        except ImportError:
            log.warning(
                "phoenix tracing requested but "
                "`openinference-instrumentation-openai` not installed — "
                "skipping."
            )
            return False
        try:
            # arize-phoenix-otel's register() signature shifted across
            # versions. We pass only the two kwargs that are stable across
            # 0.x → 1.x. run_id is recorded in the audit folder
            # (phoenix.json) so the Phoenix UI's project-scoped grouping is
            # all we need at the tracer-provider level.
            register(
                project_name=project,
                endpoint=endpoint,
            )
            OpenAIInstrumentor().instrument()
        except Exception as exc:
            # Phoenix down, network blackholed, OTel sdk mismatch — none of
            # those should crash the cron. Log and move on.
            log.warning("phoenix init failed: %s — continuing without tracing", exc)
            return False
        _initialized = True
        log.info("phoenix tracing initialised: project=%s endpoint=%s",
                 project, endpoint)
        return True
