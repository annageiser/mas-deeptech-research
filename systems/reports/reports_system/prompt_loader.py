"""Load markdown prompt templates from prompts/ at runtime.

Prompts live at /app/prompts/<name>.md inside the container (copied at build
time). Outside Docker (tests, dev) they're resolved relative to the repo
checkout. The loader tries both.
"""

from __future__ import annotations

import os
from functools import lru_cache


def _candidate_dirs() -> list[str]:
    here = os.path.dirname(os.path.abspath(__file__))
    return [
        "/app/prompts",
        os.path.normpath(os.path.join(here, "..", "prompts")),
        os.path.normpath(os.path.join(here, "..", "..", "prompts")),
    ]


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    for d in _candidate_dirs():
        path = os.path.join(d, f"{name}.md")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
    raise FileNotFoundError(f"prompt {name}.md not found under {_candidate_dirs()}")


def render_prompt(name: str, **substitutions: str) -> str:
    """Load a prompt and do safe `{{key}}` substitution.

    We DO NOT use `str.format()` because the prompt templates contain example
    structure that has literal `{...}` braces the LLM should see verbatim.
    Only `{{key}}` (double braces) is treated as a substitution point.
    """
    body = load_prompt(name)
    for k, v in substitutions.items():
        body = body.replace("{{" + k + "}}", str(v))
    return body
