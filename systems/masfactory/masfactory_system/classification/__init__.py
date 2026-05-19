"""Signal classification schema (loaded from schema.yaml)."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import yaml


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Return the parsed signal-classification schema."""
    with resources.files(__package__).joinpath("schema.yaml").open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def schema_as_prompt_block() -> str:
    """Render the schema as a compact prompt block for agent instructions."""
    schema = load_schema()
    lines = ["Signal classification taxonomy (choose exactly one dimension per signal):", ""]
    for dim in schema["dimensions"]:
        lines.append(f"- {dim['key']} ({'technical' if dim['is_technical'] else 'non-technical'}): {dim['description']}")
    lines.append("")
    lines.append("Each signal MUST quote a short verbatim snippet from the source as `evidence_quote`.")
    return "\n".join(lines)
