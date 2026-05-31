# syntax=docker/dockerfile:1.7
#
# Build context is the REPO ROOT (see docker-compose build.context: .) so we can
# copy the canonical schema.yaml from the masfactory package. All COPY paths are
# therefore repo-relative.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Zurich

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY systems/api/pyproject.toml systems/api/README.md /app/
COPY systems/api/api_app /app/api_app

# Canonical signalling-theory schema, copied from the masfactory package so the
# /api/meta endpoint cites exactly what the agents use.
COPY systems/masfactory/masfactory_system/classification/schema.yaml /app/schema.yaml

RUN python -m pip install --upgrade pip && python -m pip install .

# Build-time smoke check (no network).
RUN python -m api_app.selfcheck

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "api_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
