"""Daily report generator.

Pulls the last 24h of activity for one system from Supabase, feeds it to the
LLM with the daily-report prompt, writes the resulting markdown to
data/reports/daily/<YYYY-MM-DD>/<system>.md.
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import Settings
from .openrouter import OpenRouterClient
from .output_writer import write_report
from .prompt_loader import render_prompt
from .supabase_reader import SupabaseReader


_ZURICH = ZoneInfo("Europe/Zurich")


SYSTEM_LABELS = {
    "masfactory": ("MASFactory System A", "A"),
    "hermes": ("Hermes System B", "B"),
}


def generate_daily(*, settings: Settings, system: str) -> dict:
    if system not in SYSTEM_LABELS:
        raise ValueError(f"unknown system: {system}")
    label, letter = SYSTEM_LABELS[system]

    reader = SupabaseReader(settings)
    snapshot = reader.daily_snapshot(system=system, window_hours=24)

    now = datetime.now(_ZURICH)
    date_iso = now.strftime("%Y-%m-%d")  # CET / CEST date — matches when the cron fired

    rel_dir = f"daily/{date_iso}"
    filename = f"{system}.md"

    # v0.4.36 — zero-signal short-circuit. When the day produced 0 signals
    # the LLM had nothing useful to write about — and was previously asked
    # to produce a 4-section markdown report anyway, which (especially on
    # reasoning models with the v0.4.36 <think>-strip patch missing)
    # produced unreadable filler. The fixed template below is honest,
    # cite-able, and zero-token.
    summary = snapshot["summary"]
    if int(summary.get("signal_count", 0) or 0) == 0:
        body = _zero_signal_template(label, letter, date_iso, summary)
        path = write_report(settings.reports_dir, rel_dir, filename, body)
        return {
            "path": path,
            "snapshot_summary": summary,
            "tokens": {"input": 0, "output": 0, "calls": 0},
            "short_circuit": "zero_signals",
        }

    prompt = render_prompt("daily", system_label=label, system_letter=letter, date_iso=date_iso)
    user_payload = {
        "system_label": label,
        "system_letter": letter,
        "date_iso": date_iso,
        "summary": summary,
        "signals": _trim_signals(snapshot["signals"]),
        "actor_names_by_slug": {s: a["name"] for s, a in snapshot["actors_by_slug"].items()},
    }

    client = OpenRouterClient(settings)
    body = client.chat(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ],
        max_tokens=2048,
        temperature=0.3,
    )

    path = write_report(settings.reports_dir, rel_dir, filename, body)

    return {
        "path": path,
        "snapshot_summary": summary,
        "tokens": {"input": client.tally.input_tokens, "output": client.tally.output_tokens, "calls": client.tally.calls},
    }


def _zero_signal_template(label: str, letter: str, date_iso: str, summary: dict) -> str:
    """Fixed-template report for days where signal_count == 0.

    Honest, cite-able, and zero-token. Distinguishes the three reasons
    the day might be empty (no runs, all runs errored, runs ok but no
    signals) so an examiner can read the /reports page chronologically
    and reconstruct what happened.
    """
    n_runs = int(summary.get("run_count", 0) or 0)
    n_ok = int(summary.get("run_ok", 0) or 0)
    n_err = int(summary.get("run_error", 0) or 0)
    actors_total = int(summary.get("actors_total", 0) or 0)

    if n_runs == 0:
        cause = (
            "No cron run for this system fired in the last 24 hours. "
            "Most likely cause: host cron entry not installed or "
            "container failed to start. Check `/var/log/<system>.log` "
            "on the VPS."
        )
    elif n_err == n_runs and n_runs > 0:
        cause = (
            f"All {n_runs} run(s) ended with status='error'. "
            "Most likely cause: OpenRouter rate limit, model "
            "availability change, or upstream API outage. Per-actor "
            "diagnostics in the run's audit folder."
        )
    else:
        cause = (
            f"{n_ok} run(s) completed without error but persisted zero "
            "signals across all "
            f"{actors_total} seeded actors. "
            "Most likely cause: search backend returned empty (System B "
            "in tool-less mode — verify HERMES_TOOL_STATUS in "
            "runs.config_snapshot) OR every candidate was rejected by "
            "the Critic / attribution / dedup gates."
        )

    return (
        f"# {label} — Daily report, {date_iso}\n"
        "\n"
        "## Snapshot\n"
        "\n"
        f"- **Runs:** {n_ok} ok / {n_err} errors\n"
        f"- **New signals:** 0, across 0 of {actors_total} seeded actors\n"
        "- **Coverage gap:** every seeded actor\n"
        "- **Four-signal mix:** legitimacy 0 / customer_cocreation 0 / "
        "community_ecosystem 0 / future_trajectory 0\n"
        "- **Source mix:** n/a\n"
        "- **Sentiment:** n/a\n"
        "- **Defense flags:** engagement 0, ambivalence 0\n"
        "- **Token spend:** 0 in / 0 out / 0 calls\n"
        "\n"
        "## Notable signals today\n"
        "\n"
        "None.\n"
        "\n"
        "## Cause\n"
        "\n"
        f"{cause}\n"
        "\n"
        "## What's missing / errors\n"
        "\n"
        f"See `data/raw/runs/` (System A) or `/opt/data/state/runs/` "
        "(System B) for the relevant audit folder.\n"
        "\n"
        "---\n"
        "\n"
        "_This report was generated by the v0.4.36 zero-signal "
        "short-circuit (no LLM call) — see docs/iterations/"
        "v0.4.36-model-unification.md._\n"
    )


def _trim_signals(signals: list[dict], max_signals: int = 50) -> list[dict]:
    """Cap signals shipped to the LLM so daily reports stay bounded.

    v0.4.27: includes the v0.4.0 Ehrenthal signal_type, v0.4.19 defense
    flags, v0.4.24 sentiment_label, and the stakeholder lens. Without
    these, the LLM writing the report has no idea what categories the
    classification scheme even uses — which made every prior daily report
    silent on the four-signal mix the thesis is built on.
    """
    keys = (
        "actor_slug", "dimension", "signal_type", "is_technical", "confidence",
        "title", "summary", "evidence_quote", "source_url", "source_kind",
        "stakeholder", "sentiment_label", "sentiment_score",
        "defense_engagement", "defense_ambivalence",
    )
    return [{k: s.get(k) for k in keys} for s in signals[:max_signals]]
