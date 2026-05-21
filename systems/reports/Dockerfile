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

# Build-time smoke check: package imports + prompts load.
RUN python -m reports_system.runner build-check

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["build-check"]
