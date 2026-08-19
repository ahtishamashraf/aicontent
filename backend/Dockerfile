# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder: resolve dependencies into a virtualenv that the runtime copies.
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# The lockfile is the source of truth for the image; pyproject is only used
# to install the application package itself.
COPY requirements.lock ./
COPY pyproject.toml ./

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.lock

# ---------------------------------------------------------------------------
# Runtime: no compiler, no build tools, non-root.
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

# The model cache is a volume in production so weights are not re-downloaded
# on every deploy; see docs/DEPLOYMENT.md.
RUN mkdir -p /home/originlens/.cache/huggingface \
 && chown -R originlens:originlens /home/originlens

USER originlens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health/live || exit 1

# Graceful shutdown: uvicorn drains in-flight requests on SIGTERM.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "20"]
