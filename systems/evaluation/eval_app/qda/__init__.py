"""Qualitative-research integration via the REFI-QDA exchange standard.

The thesis empirical chapter needs a hand-coded gold set (pre-reg §5:
50 signals, stratified 4 actor categories × 4 signal types). That work
is normally done in a qualitative-coding tool — ATLAS.ti / NVivo /
MAXQDA in industry, QualCoder / OpenQDA as open-source equivalents.

This module is the round-trip between `public.signals` and any of
those tools via REFI-QDA (the Rotterdam Exchange Format for QDA — an
XML-in-ZIP container any compliant tool can import / export).

Two entry points (see `cli.py`):

  python -m eval_app.qda export …  → write a stratified .qdpx
  python -m eval_app.qda import …  → read a coded .qdpx into labels.yaml
  python -m eval_app.qda compare …  → pairwise Cohen's κ between two coding rounds

QualCoder is the recommended primary tool; OpenQDA, ATLAS.ti, NVivo,
MAXQDA all accept the same .qdpx. See
`docs/iterations/v0.4.39-qualitative-research-module.md` for the
tool-choice rationale.
"""

# Stdlib-only re-exports. The exporter pulls pandas + supabase so we
# leave it as a sub-module import for callers that actually need to
# sample from Supabase; the rest of the public surface is usable from
# any context (tests, dashboards, CI lint).
from .codebook import build_codebook
from .importer import import_coded_package
from .kappa import pairwise_kappa, stratified_summary

__all__ = [
    "build_codebook",
    "import_coded_package",
    "pairwise_kappa",
    "stratified_summary",
]
