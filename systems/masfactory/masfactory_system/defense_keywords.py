"""Defense-flag keyword backstop for System A.

VENDORED — kept structurally identical to systems/hermes/scripts/persist_signals.py
so cross-system defense-flag rates are not confounded by detection logic
differences. The comparison-validity invariant says no Python imports cross
the masfactory_system / systems/hermes boundary, so this file is a *copy*
of the Hermes equivalent rather than a shared import. When one moves, both
must move (see docs/iterations/v0.4.36-defense-symmetrisation.md if added,
or grep for DEFENSE_ENGAGEMENT_KEYWORDS across the repo).

Background: before v0.4.36 System B applied a deterministic keyword
backstop OR'd with the LLM's defense_engagement / defense_ambivalence
judgement; System A relied on the Classifier LLM alone. This created an
asymmetry in §3.5 defense-flag rates that traced to detection logic, not
to the agent's classification quality. Vendoring this module into System
A and applying the same OR at persistence time closes the asymmetry.
"""

from __future__ import annotations

from typing import Any


# Keyword lists — VERBATIM copy of
# systems/hermes/scripts/persist_signals.py L240-256 (v0.4.36 baseline).
# If you edit either side, edit both AND grep for stragglers.
DEFENSE_ENGAGEMENT_KEYWORDS: tuple[str, ...] = (
    "darpa", "afcea", "nato", "department of defense", "dod ",
    "dual-use", "dual use", "itar", "ear ", "export-control",
    "export control", "national defense", "ministry of defence",
    "ministry of defense", "armasuisse", "armaforces",
    "us army", "us navy", "us air force", "us space force",
)

DEFENSE_AMBIVALENCE_KEYWORDS: tuple[str, ...] = (
    "national security",
    "classified",
    "we cannot disclose",
    "cannot share details",
    "due to security",
    "for security reasons",
    "export restrictions",
    "restricted disclosure",
)


def detect_defense_flags(signal: dict[str, Any]) -> tuple[bool, bool]:
    """Return (engagement, ambivalence) detected purely from keywords.

    Searches title + summary + evidence_quote (all lowercased). OR'd
    with the agent's flag values at row-build time in persistence.py.
    """
    text = " ".join(
        str(signal.get(k) or "") for k in ("title", "summary", "evidence_quote")
    ).lower()
    engagement = any(kw in text for kw in DEFENSE_ENGAGEMENT_KEYWORDS)
    ambivalence = any(kw in text for kw in DEFENSE_AMBIVALENCE_KEYWORDS)
    return engagement, ambivalence
