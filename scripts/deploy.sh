#!/usr/bin/env bash
# Build, migrate, and start the production stack.
#
#   ./scripts/deploy.sh              build and deploy
#   ./scripts/deploy.sh --no-build   redeploy using existing images
#
# Safe to re-run. Migrations run as a one-shot container that must complete
# before the API and worker start, so a redeploy never races them.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mError: %s\033[0m\n' "$1" >&2; exit 1; }

# --- Preflight ---------------------------------------------------------------
step "Preflight"

# Configuration is checked before Docker: a missing secret is the operator's
# most likely mistake, and reporting it is more useful than complaining about a
# daemon they may not have started yet.
[ -f "$ENV_FILE" ] || fail "$ENV_FILE not found. Run ./scripts/generate-secrets.sh first."

# Refuse to deploy with the example values still in place. The application would
# refuse to start anyway; failing here says why in one line instead of a stack.
if grep -qE '^(ORIGINLENS_ALLOWED_HOSTS|ORIGINLENS_CORS_ORIGINS|ORIGINLENS_EMAIL_FROM|ORIGINLENS_SMTP_HOST)=.*example\.com' "$ENV_FILE"; then
  fail "$ENV_FILE still contains example.com placeholders. Edit the 'EDIT THESE' section."
fi
if grep -qiE '^ORIGINLENS_(SECRET_KEY|RATE_LIMIT_PEPPER)=.*(CHANGE_ME|dev_only)' "$ENV_FILE"; then
  fail "$ENV_FILE still contains placeholder secrets. Run ./scripts/generate-secrets.sh."
fi
if grep -qE '^ORIGINLENS_DETECTOR_BACKEND=fake' "$ENV_FILE"; then
  fail "the fake detector cannot be used in production."
fi

command -v docker >/dev/null || fail "docker is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 is not available"
docker info >/dev/null 2>&1 || fail "the Docker daemon is not reachable"

echo "  environment file: $ENV_FILE"
echo "  compose file:     docker-compose.prod.yml"

# --- Validate ----------------------------------------------------------------
step "Validating the Compose configuration"
"${COMPOSE[@]}" config --quiet
echo "  configuration is valid"

# --- Build -------------------------------------------------------------------
if [ "${1:-}" != "--no-build" ]; then
  step "Building images"
  "${COMPOSE[@]}" build --pull
else
  step "Skipping build (--no-build)"
fi

# --- Deploy ------------------------------------------------------------------
# `up` honours depends_on: the migrate container runs to completion first.
step "Starting the stack (migrations run first)"
"${COMPOSE[@]}" up -d --remove-orphans

# --- Wait for readiness ------------------------------------------------------
step "Waiting for the API to become ready"
ready=""
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" exec -T api curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [ -z "$ready" ]; then
  printf '\033[31mThe API did not become ready.\033[0m\n' >&2
  echo "Recent logs:" >&2
  "${COMPOSE[@]}" logs --tail 40 api migrate >&2
  exit 1
fi

echo "  API is ready"

# --- Report ------------------------------------------------------------------
step "Deployed"
"${COMPOSE[@]}" ps

cat <<'NEXT'

Next steps:

  Seed default settings:
    ./scripts/deploy.sh --no-build >/dev/null   # (already running)
    docker compose --env-file .env.production -f docker-compose.prod.yml \
      run --rm api python -m app.cli seed-settings

  Create an administrator:
    docker compose --env-file .env.production -f docker-compose.prod.yml \
      run --rm api python -m app.cli create-admin --email you@example.com

  Verify the real model loads:
    docker compose --env-file .env.production -f docker-compose.prod.yml \
      run --rm worker python ../scripts/model_smoke.py

The web tier listens on 127.0.0.1 only. Point your TLS-terminating reverse
proxy at it — see docs/DEPLOYMENT.md for a worked nginx and Caddy example.
NEXT
