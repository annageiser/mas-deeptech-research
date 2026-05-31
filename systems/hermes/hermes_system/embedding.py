"""Sentence embeddings for the `signals.embedding` pgvector column (System B).

Independent of System A's `embedding.py` (the two systems must not share
Python code beyond the data contract — preserves comparative validity).
Same external behaviour: same model, same dimension, same env-var gate,
so both systems' embeddings live in the same vector space and similarity
queries across the corpus are meaningful.

Gate: `HRM_EMBEDDINGS=1` (off by default). Renamed from MASF_... to keep
the env-var namespace cleanly per-system; cron operators may want to turn
embeddings on for one system at a time during evaluation.
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Optional

log = logging.getLogger(__name__)

_model = None
_model_lock = Lock()

MODEL_NAME = "BAAI/bge-base-en-v1.5"
MODEL_DIM = 768


def is_enabled() -> bool:
    return os.environ.get("HRM_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes", "on")


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from fastembed import TextEmbedding
        except ImportError:
            log.warning("fastembed not installed — embeddings disabled.")
            return None
        log.info("Loading embedding model %s (768d, BGE)...", MODEL_NAME)
        try:
            _model = TextEmbedding(model_name=MODEL_NAME)
        except Exception as exc:
            log.warning("Failed to load embedding model: %s", exc)
            return None
    return _model


def embed_text(text: str) -> Optional[list[float]]:
    if not is_enabled():
        return None
    if not text or not text.strip():
        return None
    model = _load_model()
    if model is None:
        return None
    try:
        vectors = list(model.embed([text]))
        if not vectors:
            return None
        vec = vectors[0]
        result = vec.tolist() if hasattr(vec, "tolist") else list(vec)
        if len(result) != MODEL_DIM:
            log.warning("Embedding dim mismatch: got %d, expected %d", len(result), MODEL_DIM)
            return None
        return result
    except Exception as exc:
        log.warning("embed_text failed for %s: %s", text[:60], exc)
        return None


def compose_signal_text(signal: dict) -> str:
    """Same composition logic as System A's — kept identical so a System B
    signal and a System A signal about the same event embed to nearby points."""
    parts = [
        signal.get("title") or "",
        signal.get("evidence_quote") or "",
        signal.get("summary") or "",
        f"dimension:{signal.get('dimension') or 'unknown'}",
    ]
    return "\n".join(p.strip() for p in parts if p.strip())
