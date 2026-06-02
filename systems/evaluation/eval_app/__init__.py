"""Empirical-evaluation harness for the BSc thesis.

Computes the four headline metrics from the disposition's Evaluation Framework
(§2.2.4) by reading the same Supabase the two MAS systems write to.

Public entry point: ``python -m eval_app.runner all`` — produces a
``results.json`` (machine-readable) and a ``results.md`` (thesis-ready
markdown summary) in ``data/eval/<UTC-iso>/``.
"""
