# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      tzdata \
 && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Zurich

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY hermes_system /app/hermes_system
COPY skills /app/skills

RUN python -m pip install --upgrade pip \
 && python -m pip install .

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Build-time smoke check: package imports + skill files parse.
RUN HRM_SKILLS_DIR=/app/skills python -m hermes_system.runner build-check

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["run-once"]
