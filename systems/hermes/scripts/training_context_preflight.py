"""Hermes-side preflight that materialises the editorial training layer
into per-actor context files the shell can splice into the prompt.

Reads:
  - public.manual_signals  (recommended URLs + few-shot examples per actor)
  - public.signal_sources  (enabled, due — RSS / Atom / URL)

Writes:
  - <LOGDIR>/training/<actor_slug>.txt
    A short block the shell appends to the per-actor prompt, of the form:

      MUST-CHECK URLS (curated by the operator — start here):
        - <url1>
        - <url2>

      ADDITIONAL SOURCES (RSS / Atom feeds — already enabled in the source registry):
        - <url1>
        - <url2>

  - <LOGDIR>/training/_summary.txt
    One-line summary suitable for the cron's run banner.

Mode: best-effort. If the editorial layer is unreachable, nothing is
written and the shell loop proceeds with prompts that lack the section
— Hermes behaves exactly as in v0.4.36.

Vendored from systems/hermes/scripts/training_layer.py; no cross-imports
between systems.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Local sibling.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from training_layer import load_training_layer  # type: ignore


def _render_actor_block(layer, actor_slug: str, *, max_urls: int = 8) -> str:
    recs = layer.recommended_urls_for_actor(actor_slug)
    due = [s.url for s in layer.sources_due(actor_slug=actor_slug)]
    if not recs and not due:
        return ""

    lines: list[str] = ["", "## Training-layer context (v0.4.37, operator-curated)"]
    if recs:
        lines.append("")
        lines.append("MUST-CHECK URLS (curated for this actor — start here):")
        for url in recs[:max_urls]:
            lines.append(f"  - {url}")
    if due:
        lines.append("")
        lines.append("ADDITIONAL SOURCES (enabled in registry, due for crawl):")
        for url in due[:max_urls]:
            lines.append(f"  - {url}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", required=True, help="run log directory")
    parser.add_argument("--actors-tsv", required=True, help="path to the actors.tsv shell wrote")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    training_dir = log_dir / "training"
    training_dir.mkdir(parents=True, exist_ok=True)

    layer = load_training_layer()
    n_actors = 0
    n_with_context = 0

    actors_tsv = Path(args.actors_tsv)
    if not actors_tsv.is_file():
        print(f"[training_context_preflight] actors.tsv missing: {actors_tsv}", file=sys.stderr)
        return 0

    with actors_tsv.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            slug = line.split("\t", 1)[0]
            if not slug:
                continue
            n_actors += 1
            block = _render_actor_block(layer, slug)
            out = training_dir / f"{slug}.txt"
            out.write_text(block, encoding="utf-8")
            if block:
                n_with_context += 1

    summary = (
        f"manual_signals={len(layer.manual)} sources_enabled={len(layer.sources)} "
        f"actors_total={n_actors} actors_with_context={n_with_context}\n"
    )
    (training_dir / "_summary.txt").write_text(summary, encoding="utf-8")
    print(f"[training_context_preflight] {summary.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
