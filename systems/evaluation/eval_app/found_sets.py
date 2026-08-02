"""What each run FOUND, as opposed to what it newly inserted.

WHY THIS EXISTS
---------------
`metrics/reproducibility.py` compares two runs by the signals carried in
`public.signals` under each `run_id`. That looked reasonable and is wrong,
because signals attach to the run that FIRST inserted them. The unique key on
(actor_slug, source_url, content_hash, system) means a re-run that rediscovers
the identical URL inserts nothing at all, so its run_id carries zero rows.

Measured on the production corpus, recent System A runs attach 0, 0, 1, 0 and 5
signals respectively. The two most recent were both empty, which is why
reproducibility reported zero comparisons for System A. System B's 0.155 has
the same defect in milder form: consecutive runs' newly-inserted sets are
near-disjoint by construction, since anything the first run inserted is already
in the database when the second one looks.

So the database can answer "what did this run contribute" but not "what did
this run find", and only the second question is reproducibility.

Both systems do record what they found, outside the database:

  System A  data/raw/runs/<ts>/final_attributes.json -> all_surviving_signals,
            the post-Critic set, with actor_slug and source_url per entry, plus
            the run_id so it joins back to public.runs.

  System B  <hermes_state>/state/runs/<ts>/<actor>.stdout.txt -> the agent's
            emitted JSON block. Parsed with System B's OWN parser, loaded by
            file path, so the found set is exactly what the persister saw
            rather than a re-implementation that would drift and bias the
            comparison. The evaluation harness is neither system, so reading
            System B's parser does not touch the comparison-validity invariant
            (which forbids the two SYSTEMS sharing code, not the observer
            reading either).
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


log = logging.getLogger(__name__)

# Where the two systems leave their run artefacts. Both overridable, because
# the harness may run on the host, in a container, or against a copy.
DEFAULT_MASF_AUDIT_DIR = "data/raw/runs"
DEFAULT_HERMES_RUNS_DIR = "data/hermes_state/state/runs"


@dataclass
class RunFoundSet:
    """One run's found set, independent of what was persisted."""

    system: str
    run_key: str                      # audit folder name; stable and sortable
    started_at: Optional[datetime]
    pairs: set[tuple[str, str]] = field(default_factory=set)   # (actor, url)
    actors: set[str] = field(default_factory=set)
    run_id: Optional[str] = None      # present for System A

    @property
    def n(self) -> int:
        return len(self.pairs)


def _norm_url(url: str) -> str:
    """Light normalisation so trivial variants do not read as different finds.

    Deliberately conservative: case and a trailing slash only. Anything more
    aggressive (stripping query strings, unifying www) would start merging
    genuinely different pages and inflate the reproducibility figure.
    """
    u = (url or "").strip().lower()
    return u[:-1] if u.endswith("/") and len(u) > 1 else u


# ---------------------------------------------------------------- System A --

_MASF_TS = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})")


def _parse_masf_ts(folder: str) -> Optional[datetime]:
    m = _MASF_TS.match(folder)
    if not m:
        return None
    d, hh, mm, ss = m.groups()
    try:
        return datetime.fromisoformat(f"{d}T{hh}:{mm}:{ss}").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def load_masfactory_found_sets(audit_dir: str | Path) -> list[RunFoundSet]:
    """Read System A's post-Critic found set from each audit folder."""
    root = Path(audit_dir)
    if not root.is_dir():
        log.warning("masfactory audit dir not found: %s", root)
        return []

    out: list[RunFoundSet] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        fa = folder / "final_attributes.json"
        if not fa.is_file():
            continue
        try:
            attrs = json.loads(fa.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        pairs: set[tuple[str, str]] = set()
        actors: set[str] = set()
        for sig in attrs.get("all_surviving_signals") or []:
            if not isinstance(sig, dict):
                continue
            slug = (sig.get("actor_slug") or "").strip()
            url = _norm_url(sig.get("source_url") or "")
            if slug and url:
                pairs.add((slug, url))
                actors.add(slug)

        # The cohort this run actually PROCESSED, which is the set the Loop
        # received documents for. NOT actor_pool: that is the full roster
        # regardless of --limit-actors, so a one-actor smoke run would look
        # like a forty-actor run that found almost nothing and would drag the
        # reproducibility figure down against every neighbour. Falls back to
        # the pool for older audit folders that predate documents_by_actor.
        attempted = {
            g.get("actor_slug") for g in (attrs.get("documents_by_actor") or [])
            if isinstance(g, dict) and g.get("actor_slug")
        }
        if not attempted:
            attempted = {
                a.get("slug") for a in (attrs.get("actor_pool") or [])
                if isinstance(a, dict) and a.get("slug")
            }
        out.append(RunFoundSet(
            system="masfactory",
            run_key=folder.name,
            started_at=_parse_masf_ts(folder.name),
            pairs=pairs,
            actors=attempted or actors,
            run_id=attrs.get("run_id"),
        ))
    return out


# ---------------------------------------------------------------- System B --

_HERMES_TS = re.compile(r"^(\d{8})T(\d{6})Z$")


def _parse_hermes_ts(folder: str) -> Optional[datetime]:
    m = _HERMES_TS.match(folder)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _load_hermes_parser(persister_path: str | Path):
    """Import System B's persister by path for its JSON-block extractor.

    Returns None when the file or its imports are unavailable, so the caller
    degrades to "no System B found sets" rather than crashing a run that can
    still report the other three metrics.
    """
    p = Path(persister_path)
    if not p.is_file():
        log.warning("hermes persister not found at %s", p)
        return None
    try:
        spec = importlib.util.spec_from_file_location("_hermes_persist", p)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # httpx missing, syntax drift, anything
        log.warning("could not load the hermes persister (%s): %s", p, exc)
        return None


def load_hermes_found_sets(
    runs_dir: str | Path, *, persister_path: str | Path
) -> list[RunFoundSet]:
    """Read System B's emitted signals per run, using System B's own parser."""
    root = Path(runs_dir)
    if not root.is_dir():
        log.warning("hermes runs dir not found: %s", root)
        return []
    parser = _load_hermes_parser(persister_path)
    if parser is None:
        return []

    out: list[RunFoundSet] = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        pairs: set[tuple[str, str]] = set()
        attempted: set[str] = set()

        tsv = folder / "actors.tsv"
        if tsv.is_file():
            for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
                slug = line.split("\t", 1)[0].strip()
                if slug:
                    attempted.add(slug)

        for stdout in sorted(folder.glob("*.stdout.txt")):
            name = stdout.name[: -len(".stdout.txt")]
            # The L3 fallback retry writes <actor>.fallback.stdout.txt. Both
            # belong to the same actor and the run kept whichever parsed, so
            # fold them into one actor key.
            actor = name[: -len(".fallback")] if name.endswith(".fallback") else name
            try:
                text = stdout.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            text = parser._strip_reasoning_artefacts(text)
            block = parser._extract_json_block(text)
            if not isinstance(block, dict):
                continue
            for sig in block.get("signals") or []:
                if not isinstance(sig, dict):
                    continue
                url = _norm_url(sig.get("source_url") or "")
                if url:
                    pairs.add((actor, url))

        out.append(RunFoundSet(
            system="hermes",
            run_key=folder.name,
            started_at=_parse_hermes_ts(folder.name),
            pairs=pairs,
            actors=attempted or {a for a, _ in pairs},
        ))
    return out


# ------------------------------------------------------------------ loader --

def load_all_found_sets(
    *,
    masf_audit_dir: Optional[str] = None,
    hermes_runs_dir: Optional[str] = None,
    hermes_persister: Optional[str] = None,
) -> list[RunFoundSet]:
    """Both systems' found sets, from wherever the artefacts live."""
    masf = masf_audit_dir or os.environ.get("EVAL_MASF_AUDIT_DIR", DEFAULT_MASF_AUDIT_DIR)
    herm = hermes_runs_dir or os.environ.get("EVAL_HERMES_RUNS_DIR", DEFAULT_HERMES_RUNS_DIR)
    pers = hermes_persister or os.environ.get(
        "EVAL_HERMES_PERSISTER", "systems/hermes/scripts/persist_signals.py"
    )
    runs = load_masfactory_found_sets(masf)
    runs += load_hermes_found_sets(herm, persister_path=pers)
    return runs


def summarise(runs: Iterable[RunFoundSet]) -> dict:
    by_system: dict[str, int] = {}
    for r in runs:
        by_system[r.system] = by_system.get(r.system, 0) + 1
    return {"n_runs": sum(by_system.values()), "runs_per_system": by_system}
