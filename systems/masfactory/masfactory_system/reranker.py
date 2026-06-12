"""bge-reranker cross-encoder as a cheap pre-filter ahead of the Critic.

The dense embedding (`BAAI/bge-base-en-v1.5`, see embedding.py) gives the
Persistence node semantic-dedup. It's a bi-encoder — fast, but only
*approximately* compares meaning. A cross-encoder scores a (query, doc)
pair jointly and is dramatically more accurate at relevance ranking, at
the cost of being slower per pair.

Cross-encoder use here: **does this classified signal actually concern
the actor's quantum-computing activity?** If the relevance score is below
threshold, we drop the candidate *before* the LLM Critic sees it. This
saves Critic tokens (~$0 on free-tier, but cuts run latency too) and
removes a common false-positive class — signals about an actor's
non-quantum activity that the Extractor surfaced because the actor's
name appeared on a press page.

  Model: BAAI/bge-reranker-base (~280MB ONNX via fastembed).
  Dependency: fastembed >= 0.4 (already pinned for the bi-encoder path).
  Default model: configurable via MASF_RERANKER_MODEL.
  Gating env vars:
    MASF_RERANKER=1                     turn the pre-filter on (off by default)
    MASF_RERANKER_MODEL=<hf-model-id>   override the model
    MASF_RERANKER_THRESHOLD=<float>     drop scores below this (default 0.0)

A threshold of 0.0 *scores* but does not *drop* — useful for first
calibrating the metric against the gold-standard set (task #102) before
turning on filtering in production.
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"  # fast, well-tested in fastembed
# BAAI/bge-reranker-base also available via fastembed if a stronger
# cross-encoder is wanted — set MASF_RERANKER_MODEL to switch.

_model = None
_model_lock = Lock()


def is_enabled() -> bool:
    return os.environ.get("MASF_RERANKER", "").strip().lower() in (
        "1", "true", "yes", "on"
    )


def model_name() -> str:
    return (os.environ.get("MASF_RERANKER_MODEL") or DEFAULT_MODEL).strip()


def threshold() -> float:
    """Below-threshold pairs get dropped. Clamped to [-10, 10] just in case
    a typo in .env doesn't suppress every signal silently."""
    raw = os.environ.get("MASF_RERANKER_THRESHOLD", "0.0")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.0
    return max(-10.0, min(10.0, value))


def _load_model():
    """Lazily import + cache the cross-encoder."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from fastembed import TextCrossEncoder
        except ImportError:
            log.warning(
                "fastembed.TextCrossEncoder not available — reranker disabled. "
                "Upgrade with: pip install 'fastembed>=0.4.0'"
            )
            return None
        name = model_name()
        log.info("Loading reranker model %s...", name)
        try:
            _model = TextCrossEncoder(model_name=name)
        except Exception as exc:
            log.warning("Failed to load reranker %s: %s", name, exc)
            return None
    return _model


def score_pairs(query: str, docs: list[str]) -> Optional[list[float]]:
    """Score (query, doc) for each doc. Returns one float per doc.

    Returns None if disabled, the model can't load, or `docs` is empty
    after blanking out empty strings — callers should treat None as
    "skip filtering, keep everything".
    """
    if not is_enabled():
        return None
    if not query or not query.strip() or not docs:
        return None
    model = _load_model()
    if model is None:
        return None
    try:
        # fastembed's rerank() yields one score per doc in input order.
        scores = list(model.rerank(query, list(docs)))
        return [float(s) for s in scores]
    except Exception as exc:
        log.warning("reranker score_pairs failed: %s", exc)
        return None


def compose_signal_doc(signal: dict) -> str:
    """The string the cross-encoder scores per signal.

    Mirrors compose_signal_text() in embedding.py but uses fewer fields:
    cross-encoders weight every token, so we keep the doc concise. The
    `dimension` tag is left out — the reranker should judge raw evidence,
    not the LLM's pre-existing label.
    """
    parts = [
        signal.get("title") or "",
        signal.get("evidence_quote") or "",
        signal.get("summary") or "",
    ]
    return "\n".join(p.strip() for p in parts if p.strip())


def compose_actor_query(actor: dict) -> str:
    """Build a relevance query that captures 'this actor's quantum work'.

    Cross-encoders work best with a short, declarative query. We include
    the actor's category so the reranker can distinguish 'IBM Zurich
    quantum research' from 'IBM (general)'.
    """
    name = actor.get("name") or actor.get("slug") or ""
    category = (actor.get("category") or "").replace("_", " ")
    base = f"{name} quantum computing activity"
    if category:
        base += f" ({category})"
    return base.strip()
