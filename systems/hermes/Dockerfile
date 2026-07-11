# Real NousResearch Hermes Agent — thesis System B (production CLI variant).
#
# v0.4.20: switched from building hermes-upstream:local from the git submodule
# (10-15 min, 4.65 GB image) to pulling the OFFICIAL published image from
# Docker Hub (~1 GB, downloads in ~1 min). The submodule at ./upstream
# stays in the repo as a source-code reference for the thesis defence and
# for inspecting upstream's actual implementation, but the build chain no
# longer touches it.
#
# Image is digest-pinned to v2026.6.5 for reproducibility — the thesis
# will cite this exact SHA. If you want to bump, replace the digest below.
#
# Build the wrapper (fast — ~30 s):
#
#     docker compose build hermes
#
# At runtime the wrapper image runs:
#     /opt/swiss-quantum/scripts/collect_all_actors.sh
#       → loops actors → `hermes chat -q` → persist_signals.py
#
# Comparison-validity invariant: System A (MASFactory) and System B
# (hermes) MUST share no Python code beyond the Supabase schema.
# Our wrapper scripts use only `httpx` + `pyyaml` from the upstream venv.
# No imports from masfactory_system are permitted.

# v0.4.20 — pin to the official Hermes Agent v2026.6.5, digest-locked for
# thesis reproducibility. The upstream submodule is kept as a source
# reference but is no longer in the build path. Bumping = replace both
# the tag and the digest.
FROM nousresearch/hermes-agent:v2026.6.5@sha256:9ad3b04ec916ea2c2da22358fd43b024c788d74073210695af88bfc2e63869b4

# Switch to root briefly to install our wrapper bits — the upstream
# image drops to UID 10000 (hermes) by default via s6-overlay.
USER root

# v0.4.14: install ddgs (DuckDuckGo Search) into the upstream venv.
# Upstream's web_tools.py supports ddgs as a free, no-API-key fallback
# but does NOT install it by default. With ddgs in the venv, web_search
# works unlimited and free — no Firecrawl/Tavily/Brave/etc keys needed.
# This unlocks DAILY cron without burning anyone's paid quota.
#
# web_extract is NOT covered by ddgs (it's search-only). The agent uses
# search snippets as evidence when deep page-reading is unavailable.
#
# Upstream uses `uv` to manage the venv (no `pip` binary inside .venv).
# VIRTUAL_ENV points uv at the right venv without needing --python flag.
ENV VIRTUAL_ENV=/opt/hermes/.venv
RUN uv pip install --no-cache-dir ddgs \
    && chown -R hermes:hermes /opt/hermes/.venv

# v0.4.20: install fastembed + onnxruntime so the Hermes persister can
# compute the SAME 768d BGE embedding as MASFactory does — required for
# cross-system semantic dedup. Gated at runtime by HRM_EMBEDDINGS=1.
# Adds ~210 MB to the image but unlocks the comparison-validity fix.
RUN uv pip install --no-cache-dir 'fastembed>=0.4.0' \
    && chown -R hermes:hermes /opt/hermes/.venv

# v0.4.24: install vaderSentiment so the Hermes persister can score signals
# with the SAME lexicon + thresholds as MASFactory does. Tiny dep (~120 KB),
# no model download, no native code. Gated at runtime by HRM_SENTIMENT
# (default ON; disable with HRM_SENTIMENT=0).
RUN uv pip install --no-cache-dir 'vaderSentiment>=3.3.2' \
    && chown -R hermes:hermes /opt/hermes/.venv

# v0.5.1 (Stage 2b): install selectolax so System B can extract full page text
# with the SAME parser + method System A uses (collection/website.py). Light,
# reliable, no browser — the opposite of the abandoned scrapling/Playwright
# path. Feeds the local full-text web-extract provider installed below.
RUN uv pip install --no-cache-dir selectolax \
    && chown -R hermes:hermes /opt/hermes/.venv

# v0.5.1 (Stage 2b): install the local full-text web-extract provider into the
# image's BUNDLED plugins dir so it auto-loads as a `backend` plugin (bundled
# backends load without an explicit `plugins.enable`). The target dir is
# resolved the SAME way upstream does (hermes_cli.plugins.get_bundled_plugins_dir):
# $HERMES_BUNDLED_PLUGINS if set, else <hermes_cli parent>/plugins. The final
# import+capability assertion fails the build loudly if the path/layout ever
# drifts on a base-image bump — otherwise the agent would silently revert to
# snippet-only extraction with no error.
COPY plugins/web/localextract /opt/swiss-quantum/plugins/web/localextract
RUN set -eu; \
    PLUGROOT="${HERMES_BUNDLED_PLUGINS:-$(/opt/hermes/.venv/bin/python -c 'import hermes_cli, os; print(os.path.join(os.path.dirname(os.path.dirname(hermes_cli.__file__)), "plugins"))')}"; \
    echo "[localextract] bundled plugins dir: $PLUGROOT"; \
    mkdir -p "$PLUGROOT/web/localextract"; \
    cp -r /opt/swiss-quantum/plugins/web/localextract/. "$PLUGROOT/web/localextract/"; \
    chown -R hermes:hermes "$PLUGROOT/web/localextract"; \
    /opt/hermes/.venv/bin/python -c "import plugins.web.localextract.provider as m; assert m.LocalExtractProvider().supports_extract(); print('[localextract] provider import + capability OK')"

# v0.5.1 (Stage 2b): teach upstream's extract-backend router that `localextract`
# is an available backend. `tools.web_tools._is_backend_available()` HARDCODES
# the built-in backend names and returns False for anything else — so without
# this our `web.extract_backend: localextract` is silently dropped and the agent
# reverts to snippet-only. The patch script APPENDS a wrapper to the module
# (robust to upstream body edits) rather than editing the function in place. It
# applies at IMPORT time — before any plugin discovery — so even a `web_extract`
# issued before the first `web_search` resolves the backend correctly (the
# discovery-timed runtime monkeypatch this replaces could not). Kept as a real
# script (not a RUN heredoc) so the build doesn't depend on BuildKit. Idempotent
# (marker-guarded) + asserted in a fresh interpreter: only env-INDEPENDENT cases
# (localextract recognised; unknown name still False) — real backends like
# searxng are env-gated (SEARXNG_URL is unset at build time) so aren't asserted.
COPY scripts/patch_web_tools_backend.py /tmp/patch_web_tools_backend.py
RUN /opt/hermes/.venv/bin/python /tmp/patch_web_tools_backend.py \
    && /opt/hermes/.venv/bin/python -c "import tools.web_tools as m; assert m._is_backend_available('localextract') is True; assert m._is_backend_available('definitely-not-a-backend') is False; print('[localextract] _is_backend_available shim OK')" \
    && rm -f /tmp/patch_web_tools_backend.py

# Install the Swiss-quantum skill into the agent's skills directory.
# The agent picks up skills from $HERMES_HOME/skills/* at startup.
COPY skills/collect-swiss-quantum-signals \
     /opt/swiss-quantum/skills/collect-swiss-quantum-signals

# Our cron-mode config. Copied into $HERMES_HOME/config.yaml on first
# boot by the seed script below.
COPY config/cli-config.yaml /opt/swiss-quantum/config.yaml

# Wrapper scripts that turn the agent into a signal-collection cron job.
COPY scripts/ /opt/swiss-quantum/scripts/
RUN chmod +x /opt/swiss-quantum/scripts/*.sh /opt/swiss-quantum/scripts/*.py 2>/dev/null || true

# Seed script — runs as cont-init.d so it executes ONCE before s6
# starts services.
COPY scripts/seed-hermes-home.sh /etc/cont-init.d/03-seed-swiss-quantum
RUN chmod +x /etc/cont-init.d/03-seed-swiss-quantum

# Drop back to the hermes user so the supervised services run unprivileged.
USER hermes

# Default to our cron loop instead of interactive chat. Override with
# `docker run ... hermes chat` for interactive debugging.
CMD ["/opt/swiss-quantum/scripts/collect_all_actors.sh"]
