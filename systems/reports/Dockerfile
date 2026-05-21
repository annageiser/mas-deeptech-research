# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      tzdata \
 && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Zurich

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY reports_system /app/reports_system
COPY prompts /app/prompts

RUN python -m pip install --upgrade pip \
 && python -m pip install .

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# The repo is bind-mounted from the host at /repo (see docker-compose.yml)
# so the weekly-thesis report can read its git log. The container runs as
# root by default; the host repo is owned by `annageiser` (uid 1000). git
# treats that as untrusted unless we whitelist the path.
RUN git config --global --add safe.directory /repo

# Build-time smoke check: package imports + prompts load.
RUN python -m reports_system.runner build-check

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["build-check"]
