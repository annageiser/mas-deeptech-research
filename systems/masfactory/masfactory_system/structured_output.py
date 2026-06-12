"""Structured-output discipline for the Classifier → Persistence boundary.

Before v0.4.22 the persister parsed `classified_json` with json.loads, then
iterated over the resulting list of dicts treating every expected field as
implicitly present. The contract was enforced only by the LLM's good
behaviour; a malformed entry (bad confidence type, missing dimension)
either crashed downstream or silently inserted a corrupted row.

This module makes the contract explicit:

  - `validate_classified_batch(raw)` runs every entry through the
    ClassifiedSignal Pydantic model. Returns `(valid_dicts, invalid_records)`.
    valid_dicts are dumps of the validated models — same shape as before but
    with type coercion (e.g. confidence "0.8" → 0.8) and defaults applied
    (signal_type filled from dimension if absent).
  - `instructor_repair(raw_json, settings)` is the optional re-prompt path,
    gated by env var `MASF_INSTRUCTOR_REPAIR=1`. Uses the `instructor`
    library to ask OpenRouter to re-emit the SAME content as a validated
    JSON object. Costs extra tokens — off by default.

The validation half ships unconditionally and has zero token cost. The
repair half is opt-in for thesis runs where data integrity matters more
than the marginal token budget.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import ValidationError

from .classification import normalise_dimension, signal_type_for_dimension
from .schema import ClassifiedSignal


def _repair_enabled() -> bool:
    return os.environ.get("MASF_INSTRUCTOR_REPAIR", "").strip().lower() in (
        "1", "true", "yes", "on"
    )


def _coerce_and_fill(raw: dict[str, Any]) -> dict[str, Any]:
    """Best-effort field normalisation BEFORE pydantic validates.

    Two cheap fixes that account for most LLM-side drift:
      - dimension: accept v0.3.0 keys and migrate via normalise_dimension.
      - signal_type: if absent, derive from the (normalised) dimension.
    """
    out = dict(raw or {})
    dim = out.get("dimension")
    if isinstance(dim, str) and dim:
        out["dimension"] = normalise_dimension(dim)
    if not out.get("signal_type"):
        norm_dim = out.get("dimension")
        if isinstance(norm_dim, str):
            out["signal_type"] = signal_type_for_dimension().get(norm_dim)
    return out


def validate_classified_batch(
    raw_classified: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate each entry against ClassifiedSignal.

    Returns:
      (valid_dicts, invalid_records)
        - valid_dicts: list of model_dump() outputs — JSON-ready dicts that
          downstream code can treat as guaranteed-shape.
        - invalid_records: list of {"raw": <input>, "errors": [<pydantic>]}.
          One entry per drop; safe to write to the audit folder.
    """
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for raw in raw_classified or []:
        if not isinstance(raw, dict):
            invalid.append({"raw": raw, "errors": [{"msg": "not a JSON object"}]})
            continue
        try:
            model = ClassifiedSignal.model_validate(_coerce_and_fill(raw))
            valid.append(model.model_dump(mode="json"))
        except ValidationError as exc:
            invalid.append({"raw": raw, "errors": exc.errors()})
    return valid, invalid


def instructor_repair_available() -> bool:
    """True iff `MASF_INSTRUCTOR_REPAIR=1` AND the instructor lib imports.

    Kept as a single-flag check so the persistence node can short-circuit
    cheaply without paying the instructor import cost in the common case.
    """
    if not _repair_enabled():
        return False
    try:
        import instructor  # noqa: F401
    except ImportError:
        return False
    return True


def instructor_repair(raw_entry: dict[str, Any]) -> dict[str, Any] | None:
    """Re-prompt the LLM to emit a SCHEMA-valid version of `raw_entry`.

    Reads OPENROUTER_API_KEY / OPENROUTER_BASE_URL / MASF_MODEL_MAIN from
    environment so persistence.py can call this without threading the
    Settings object through the CustomNode attrs.

    Returns:
      - dict (model_dump output) if the LLM emits a valid ClassifiedSignal.
      - None if instructor isn't available, the call fails, or the result
        still fails validation. Caller falls back to dropping the entry.

    Cost: one Chat Completions call per invalid entry. Always gated by
    MASF_INSTRUCTOR_REPAIR=1. Use sparingly.
    """
    if not instructor_repair_available():
        return None
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    base_url = (os.environ.get("OPENROUTER_BASE_URL") or
                "https://openrouter.ai/api/v1").strip()
    model = (os.environ.get("MASF_MODEL_MAIN") or
             "nvidia/nemotron-nano-9b-v2:free").strip()
    if not api_key:
        return None
    try:
        import instructor
        from openai import OpenAI

        client = instructor.from_openai(OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=90.0,
        ))
        result: ClassifiedSignal = client.chat.completions.create(
            model=model,
            response_model=ClassifiedSignal,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Re-emit the user's classification as a valid "
                        "ClassifiedSignal. Preserve every original field "
                        "verbatim; only fix type errors (e.g. confidence "
                        "as a number, dimension as a known key)."
                    ),
                },
                {"role": "user", "content": str(raw_entry)},
            ],
            max_retries=2,
        )
        return result.model_dump(mode="json")
    except Exception:
        # Repair is best-effort. If anything goes wrong (network, validation
        # still fails after retries, OpenRouter quirk), give up and let the
        # caller drop the entry — better than crashing the cron.
        return None
