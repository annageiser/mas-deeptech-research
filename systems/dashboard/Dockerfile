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
COPY dashboard_app /app/dashboard_app

RUN python -m pip install --upgrade pip \
 && python -m pip install .

# Streamlit telemetry off, no usage stats; serve on all interfaces (Caddy
# proxies the public hostname → this container on the internal network).
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8501

CMD ["streamlit", "run", "dashboard_app/Home.py", "--server.port=8501", "--server.address=0.0.0.0"]
