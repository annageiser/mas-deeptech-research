#!/usr/bin/env python3
"""Build-time patch: teach upstream's extract-backend router about localextract.

v0.5.1 (Stage 2b). `tools.web_tools._is_backend_available()` HARDCODES the
built-in backend names (exa/parallel/firecrawl/tavily/searxng/brave-free/ddgs/
xai) and returns False for anything else — so our `web.extract_backend:
localextract` would be silently dropped and the agent would revert to
snippet-only. We APPEND a wrapper that redefines `_is_backend_available` to
recognise `localextract` (delegating to the original for every other name).

Why append at build time rather than monkeypatch from the plugin: `web_extract`
resolves the backend (`_get_extract_backend`) BEFORE it triggers plugin
discovery (`_ensure_web_plugins_loaded`). Discovery is lazy, so a plugin-time
monkeypatch would miss a `web_extract` issued before the first `web_search`. The
appended wrapper applies at module import — before any discovery — so the first
extract resolves correctly regardless of tool order.

Idempotent (marker-guarded). Run from the Dockerfile; a separate fresh-interpreter
assertion verifies the behaviour so a base-image change that moved/renamed the
symbol fails the build loudly. Not a runtime dependency — this only runs at build.
"""
from __future__ import annotations

import sys

MARKER = "# >>> localextract extract-backend shim (thesis v0.5.1)"
SHIM = (
    "\n\n" + MARKER + "\n"
    "_localextract_orig_is_backend_available = _is_backend_available\n"
    "def _is_backend_available(backend):\n"
    "    if backend == 'localextract':\n"
    "        return True\n"
    "    return _localextract_orig_is_backend_available(backend)\n"
    "# <<< localextract extract-backend shim\n"
)


def main() -> int:
    import tools.web_tools as web_tools  # locate the installed module file

    path = web_tools.__file__
    with open(path, encoding="utf-8") as fh:
        src = fh.read()

    if "_is_backend_available" not in src:
        print(
            "[localextract] FATAL: upstream symbol _is_backend_available not "
            f"found in {path} — base image changed; refusing to patch.",
            file=sys.stderr,
        )
        return 1

    if MARKER in src:
        print(f"[localextract] _is_backend_available shim already present in {path}")
        return 0

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src + SHIM)
    print(f"[localextract] appended _is_backend_available shim to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
