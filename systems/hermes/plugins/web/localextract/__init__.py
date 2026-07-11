"""Local full-text extract plugin — bundled, auto-loaded (v0.5.1, Stage 2b).

Registers :class:`LocalExtractProvider` so the agent's built-in ``web_extract``
tool can pull full page text (httpx + selectolax) for System B, matching System
A's extraction method. Search stays on SearXNG; this provider is extract-only.

BACKEND RECOGNITION (why there's no runtime shim here)
------------------------------------------------------
Upstream's per-capability router (``tools.web_tools._get_capability_backend``)
only returns a configured ``web.extract_backend`` when
``_is_backend_available(name)`` is True — and that function HARDCODES the
built-in backend names, returning False for anything else. Teaching it about
``localextract`` is done in the **Dockerfile** by appending a 6-line wrapper to
``tools/web_tools.py`` at build time (idempotent + asserted). That was chosen
over a runtime monkeypatch installed from this module because ``web_extract``
resolves the backend (``web_tools.py:_get_extract_backend``) BEFORE it triggers
plugin discovery (``_ensure_web_plugins_loaded``) — so a monkeypatch installed
at discovery time would miss a ``web_extract`` issued before the first
``web_search``. The build-time append applies at module import, before any
discovery, so the very first extract resolves correctly. See
docs/iterations/v0.5.1-stage2b-system-b-fulltext.md §2.1.
"""

from __future__ import annotations

from plugins.web.localextract.provider import LocalExtractProvider


def register(ctx) -> None:
    """Register the local full-text extract provider with the plugin context."""
    ctx.register_web_search_provider(LocalExtractProvider())
