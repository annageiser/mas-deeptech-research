# Real NousResearch Hermes Agent — thesis System B (production CLI variant).
#
# Build context: this Dockerfile builds the upstream hermes-agent image
# from the git submodule at ./upstream and adds our skill + cron
# entrypoint. We DO NOT use the published `nousresearch/hermes-agent`
# image because (a) it doesn't pin a version yet on Docker Hub and
# (b) the submodule gives us a frozen SHA — reproducibility wins.
#
# Build the upstream image first (10-15 min, ~1.5 GB):
#
#     docker build -t hermes-upstream:local systems/hermes/upstream
#
# Then build this wrapper:
#
#     docker compose build hermes
#
# At runtime the wrapper image runs:
#     entrypoint.sh  →  loops actors  →  hermes chat -q  →  persist_signals.py
#
# Comparison-validity invariant: System A (MASFactory) and System B
# (hermes) MUST share no Python code beyond the Supabase schema.
# This image installs a separate Python venv via the upstream image's uv;
# our wrapper scripts use only `httpx` + `pyyaml` from the system python.
# No imports from masfactory_system / hermes_system are permitted.

ARG UPSTREAM_TAG=local
FROM hermes-upstream:${UPSTREAM_TAG}

# Switch to root briefly to install our wrapper bits — the upstream
# image drops to UID 10000 (hermes) by default via s6-overlay.
USER root

# Our wrapper scripts use httpx + pyyaml — the upstream image already
# has both because they're transitive deps of the agent. We do not
# `uv pip install` anything else to avoid mutating the upstream venv.

# v0.4.14: install ddgs (DuckDuckGo Search) into the upstream venv.
# Upstream's web_tools.py supports ddgs as a free, no-API-key fallback
# but does NOT install it by default. With ddgs in the venv, web_search
# works unlimited and free — no Firecrawl/Tavily/Brave/etc keys needed.
# This unlocks DAILY cron without burning anyone's paid quota.
#
# web_extract is NOT covered by ddgs (it's search-only). The agent will
# use search snippets as evidence when deep page-reading is unavailable.
RUN /opt/hermes/.venv/bin/python -m pip install --no-cache-dir ddgs \
    && chown -R hermes:hermes /opt/hermes/.venv

# Install the Swiss-quantum skill into the agent's skills directory.
# The agent picks up skills from $HERMES_HOME/skills/* at startup.
# HERMES_HOME defaults to /opt/data (volume-mounted, so we copy the
# skill at runtime via stage2-hook, not at build time).
COPY skills/collect-swiss-quantum-signals \
     /opt/swiss-quantum/skills/collect-swiss-quantum-signals

# Our cron-mode config. Copied into $HERMES_HOME/config.yaml on first
# boot by the seed script below.
COPY config/cli-config.yaml /opt/swiss-quantum/config.yaml

# Wrapper scripts that turn the agent into a signal-collection cron job.
COPY scripts/ /opt/swiss-quantum/scripts/
RUN chmod +x /opt/swiss-quantum/scripts/*.sh /opt/swiss-quantum/scripts/*.py 2>/dev/null || true

# Seed script — runs as cont-init.d so it executes ONCE before s6
# starts services. Copies our skill + config into the volume-mounted
# $HERMES_HOME, but only if they don't already exist (idempotent —
# user edits are not clobbered on restart).
COPY scripts/seed-hermes-home.sh /etc/cont-init.d/03-seed-swiss-quantum
RUN chmod +x /etc/cont-init.d/03-seed-swiss-quantum

# Drop back to the hermes user so the supervised services run unprivileged.
USER hermes

# Default to our cron loop instead of interactive chat. Override with
# `docker run ... hermes chat` for interactive debugging.
CMD ["/opt/swiss-quantum/scripts/collect_all_actors.sh"]
