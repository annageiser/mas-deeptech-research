"""v0.4.24 — VADER-based sentiment scoring for signals (task C.4).

Why VADER (Hutto & Gilbert 2014):
  - Lexicon-based — no LLM tokens, no API call, ~1ms per signal on CPU.
  - Tuned on social-media + news-style English (which matches our corpus).
  - Battle-tested citation for the thesis (Hutto, C.J. & Gilbert, E.E.,
    2014. VADER: A Parsimonious Rule-based Model for Sentiment Analysis
    of Social Media Text. ICWSM-14).
  - Returns a `compound` score in [-1, 1] plus pos/neu/neg breakdown.
    We persist `compound` (one number) plus a categorical label derived
    from it — easy to filter on without a continuous range query.

We compute sentiment over evidence_quote + summary (title omitted: it's
often headline-shorthand that confuses lexicon scoring).

Defaults ON: the score is cheap and the column is nullable, so there's
no downside to having it for the whole corpus. Opt out with
MASF_SENTIMENT=0 if you want to suppress it.

Cross-system parity: System B (Hermes) vendors the same compose-helper +
label-bucketing thresholds in persist_signals.py so cross-system
sentiment comparisons aren't confounded by different scoring schemes.
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Optional

log = logging.getLogger(__name__)

# Label thresholds — match VADER's own paper. Both systems use these.
POS_THRESHOLD = 0.05
NEG_THRESHOLD = -0.05

_analyzer = None
_analyzer_lock = Lock()


def is_enabled() -> bool:
    """Defaults ON. Disable with `MASF_SENTIMENT=0|false|no|off`."""
    raw = os.environ.get("MASF_SENTIMENT", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


def _load_analyzer():
    global _analyzer
    if _analyzer is not None:
        return _analyzer
    with _analyzer_lock:
        if _analyzer is not None:
            return _analyzer
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        except ImportError:
            log.warning(
                "vaderSentiment not installed — sentiment scoring disabled. "
                "Install with: pip install vaderSentiment>=3.3.2"
            )
            return None
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def compose_sentiment_text(signal: dict) -> str:
    """The string we score. Evidence + summary; title omitted."""
    parts = [
        signal.get("evidence_quote") or "",
        signal.get("summary") or "",
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def label_for(score: Optional[float]) -> Optional[str]:
    """Bucket a VADER compound score into 'positive'/'neutral'/'negative'.
    Returns None when score is None so the caller can skip the column."""
    if score is None:
        return None
    if score >= POS_THRESHOLD:
        return "positive"
    if score <= NEG_THRESHOLD:
        return "negative"
    return "neutral"


def score_signal(signal: dict) -> Optional[tuple[float, str]]:
    """Return (compound_score, label) for `signal`, or None if disabled,
    the analyzer can't load, or the composed text is empty.

    Rounded to 4 decimal places so the persisted column stays compact."""
    if not is_enabled():
        return None
    text = compose_sentiment_text(signal)
    if not text:
        return None
    analyzer = _load_analyzer()
    if analyzer is None:
        return None
    try:
        scores = analyzer.polarity_scores(text)
        compound = round(float(scores.get("compound", 0.0)), 4)
        return compound, label_for(compound) or "neutral"
    except Exception as exc:
        log.warning("sentiment score failed: %s", exc)
        return None
