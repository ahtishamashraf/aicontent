# syntax=docker/dockerfile:1
#
# One file, two runtime targets. The API and the worker share every stage up to
# the final one, so they cannot drift in dependencies and neither depends on the
# other's image having been built first.
#
#   docker build --target api    -t originlens-api:latest    ./backend
#   docker build --target worker -t originlens-worker:latest ./backend

# ---------------------------------------------------------------------------
# Builder: resolve dependencies into a virtualenv the runtime copies.
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# The lockfile is the source of truth for what ships; pyproject is only used to
# install the application package itself.
COPY requirements.lock ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.lock

# Optional machine-learning dependencies. Enabled with:
#   docker build --build-arg INCLUDE_ML=true ...
# Off by default because the CUDA wheels add roughly 2 GB to the image and the
# API never loads them.
ARG INCLUDE_ML=false
COPY requirements-ml.lock ./
RUN if [ "$INCLUDE_ML" = "true" ]; then \
      /opt/venv/bin/pip install --no-cache-dir -r requirements-ml.lock; \
    fi

# ---------------------------------------------------------------------------
# Runtime base: no compiler, no build tools, non-root.
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/home/originlens/.cache/huggingface

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl libpq5 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 originlens

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=originlens:originlens . .

# The model cache is a volume in production so weights survive a redeploy.
RUN mkdir -p /home/originlens/.cache/huggingface \
 && chown -R originlens:originlens /home/originlens

USER originlens

# ---------------------------------------------------------------------------
# api
# ---------------------------------------------------------------------------
FROM runtime AS api

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health/live || exit 1

# uvicorn drains in-flight requests on SIGTERM rather than cutting them off.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "20"]

# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------
FROM runtime AS worker

# Concurrency and prefetch are pinned in app/tasks/worker.py: a transformer
# checkpoint is one full copy of the weights per process, so extra processes
# cost RAM rather than buying throughput. Scale by adding replicas.
HEALTHCHECK --interval=60s --timeout=15s --start-period=60s --retries=3 \
  CMD celery -A app.tasks.worker.celery_app inspect ping -d "celery@$HOSTNAME" || exit 1

CMD ["celery", "-A", "app.tasks.worker.celery_app", "worker", \
     "--loglevel=INFO", "--concurrency=1", "--prefetch-multiplier=1"]

# ---------------------------------------------------------------------------
# migrate: a one-shot container that brings the schema to head and exits.
# Compose runs this to completion before starting the API and worker, so
# migrations happen exactly once rather than racing across replicas.
# ---------------------------------------------------------------------------
FROM runtime AS migrate

CMD ["alembic", "upgrade", "head"]
