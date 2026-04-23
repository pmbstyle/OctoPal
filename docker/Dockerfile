FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io ca-certificates curl wget jq \
    && python -m pip install --no-cache-dir playwright \
    && playwright install-deps chromium \
    && playwright install chromium \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

FROM base AS worker

# The launcher invokes: python -m octopal.workers.entrypoint <spec>
# Keeping ENTRYPOINT empty to allow explicit command in DockerLauncher.
