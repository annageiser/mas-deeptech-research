"""Lightweight sentence embeddings for the `signals.embedding` pgvector column.

The schema reserves `vector(768)` on `public.signals` (see schema.sql). This
module fills it. It's intentionally:

  - **Optional** — gated by the `MASF_EMBEDDINGS` env var (off by default).
    Cron runs that don't need embeddings pay zero model-load cost.
  - **Lightweight** — uses `fastembed` (ONNX runtime, ~80MB native lib +
    ~210MB model) rather than `sentence-transformers` (pulls in torch,
    ~500MB). No GPU. CPU-only embed is ~0.8s per signal cold-start, ~0.05s
    per signal warm. Acceptable for daily-cron batches of ~50 signals.
  - **Singleton** — the ONNX model loads ~7s cold-start; we cache it at
    module level so the per-run cost is paid once, not per-signal.

Model: **`BAAI/bge-base-en-v1.5`** (768d). Rationale:
  - 768d matches the existing `vector(768)` schema column verbatim — no
    migration. (The schema dimension was chosen before this module existed;
    fixing the model to that dimension preserves backward-compatibility.)
  - English-only — the dominant language of our corpus (arXiv abstracts,
    EPFL/ETH/IBM-CH English press releases, Swiss quantum companies'
    English-first comms). Multilingual alternatives at the same dimension
    (e.g. paraphrase-multilingual-mpnet-base-v2, 1GB) are 5× the image
    size for a modest quality lift on the German/French slice.
  - Battle-tested (BGE family is the SOTA reference for compact retrieval
    embeddings as of 2026).

Use cases unlocked by populating this column:
  - Semantic deduplication in the Critic (cosine similarity > 0.92 → drop).
  - "Find related signals" links in the dashboard / API.
  - Nearest-neighbour search via pgvector's ivfflat index (the schema's
    commented-out `create index using ivfflat` becomes runnable once we
    have non-null embeddings).
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Optional

log = logging.getLogger(__name__)

# Module-level singleton — loaded once per process. None until first use.
_model = None
_model_lock = Lock()

MODEL_NAME = "BAAI/bge-base-en-v1.5"
MODEL_DIM = 768  # must equal the `vector(N)` column in schema.sql


def is_enabled() -> bool:
    """Embeddings are off by default. Set `MASF_EMBEDDINGS=1` to turn on.
    Case-insensitive: `1`, `true`, `yes`, `on` (any case) all turn it on."""
    return os.environ.get("MASF_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes", "on")


def _load_model():
    """Lazily import fastembed and cache the loaded model.

    Import is lazy so the module-level import in callers (persistence.py)
    doesn't pull in onnxruntime if embeddings are disabled.
    """
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            # Local import: fastembed has a non-trivial native (onnxruntime)
            # cold-start, so we only pay for it when needed.
            from fastembed import TextEmbedding
        except ImportError:
            log.warning(
                "fastembed not installed — embeddings disabled. "
                "Install with: pip install fastembed>=0.4.0"
            )
            return None
        log.info("Loading embedding model %s (768d, BGE)...", MODEL_NAME)
        try:
            _model = TextEmbedding(model_name=MODEL_NAME)
        except Exception as exc:
            # Network failure during first-run model download, or ONNX runtime
            # issue on this CPU arch. Don't crash the pipeline — signal will
            # be inserted with embedding=NULL.
            log.warning("Failed to load embedding model: %s", exc)
            return None
    return _model


def embed_text(text: str) -> Optional[list[float]]:
    """Return a 768-dim embedding for `text`, or None if embeddings are
    disabled or the model failed to load.

    `None` (rather than a zero vector or exception) is the right shape:
    persistence treats it as "leave the column NULL", which keeps the row
    insertable and the downstream dedup query (`is not null`-gated) sound.
    """
    if not is_enabled():
        return None
    if not text or not text.strip():
        return None
    model = _load_model()
    if model is None:
        return None
    try:
        # fastembed returns a generator of numpy arrays; we want one float list.
        vectors = list(model.embed([text]))
        if not vectors:
            return None
        vec = vectors[0]
        # tolist() on numpy → list[float]; guard if upstream changes shape.
        result = vec.tolist() if hasattr(vec, "tolist") else list(vec)
        if len(result) != MODEL_DIM:
            log.warning("Embedding dim mismatch: got %d, expected %d", len(result), MODEL_DIM)
            return None
        return result
    except Exception as exc:
        log.warning("embed_text failed for %s: %s", text[:60], exc)
        return None


def compose_signal_text(signal: dict) -> str:
    """The string a Signal embeds as.

    Concatenates the most semantically-loaded fields. Title carries the
    headline meaning; evidence_quote carries the concrete claim; summary
    carries the broader context. Dimension is included as a one-token tag so
    the embedding distinguishes a 'funding' signal from a 'hiring' signal
    even when the surface text is similar.
    """
    parts = [
        signal.get("title") or "",
        signal.get("evidence_quote") or "",
        signal.get("summary") or "",
        f"dimension:{signal.get('dimension') or 'unknown'}",
    ]
    return "\n".join(p.strip() for p in parts if p.strip())
