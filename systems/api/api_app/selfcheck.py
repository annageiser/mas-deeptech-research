"""Build-time smoke check: import the app + scoring with no network, print routes.

If anything is mis-wired, the import raises and the Docker build fails — so a
broken image never ships (same pattern as the other containers' build-check).
"""

from __future__ import annotations


def main() -> int:
    from .main import app  # triggers full import chain
    from .meta import meta_payload

    routes = sorted(r.path for r in app.routes if getattr(r, "path", "").startswith("/api"))
    payload = meta_payload()
    print("ok: api_app imports")
    print(f"routes: {routes}")
    print(f"meta dimensions: {len(payload.get('dimensions', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
