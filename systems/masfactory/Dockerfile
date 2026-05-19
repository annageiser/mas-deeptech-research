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

# Copy the full package (pyproject.toml needs README.md and the package source).
COPY pyproject.toml README.md /app/
COPY masfactory_system /app/masfactory_system

RUN python -m pip install --upgrade pip \
 && python -m pip install .

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Build-time smoke check: the image will not build if the graph fails to compile.
RUN python -m masfactory_system.runner build-check

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["run-once"]
