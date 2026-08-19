#!/usr/bin/env bash
# Every quality gate, in one command.
#
# Each gate runs even if an earlier one fails, so a single run reports every
# problem rather than stopping at the first. The exit status is non-zero if any
# gate failed, and a summary is printed at the end.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PASSED=()
FAILED=()
SKIPPED=()

run() {
  local name="$1"; shift
  echo
  echo "──────────────────────────────────────────────────────────────────────"
  echo "==> $name"
  echo "──────────────────────────────────────────────────────────────────────"
  if "$@"; then
    PASSED+=("$name")
  else
    FAILED+=("$name")
  fi
}

skip() {
  echo
  echo "==> SKIPPED: $1 ($2)"
  SKIPPED+=("$1 ($2)")
}

BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

if [ ! -d "$BACKEND/.venv" ]; then
  echo "The backend virtualenv is missing. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

backend() { (cd "$BACKEND" && . .venv/bin/activate && "$@"); }
frontend() { (cd "$FRONTEND" && "$@"); }

# --- Backend -----------------------------------------------------------------
run "backend: format check"   backend ruff format --check .
run "backend: ruff"           backend ruff check .
run "backend: mypy"           backend mypy app detection
run "backend: import/startup" backend python -c "from app.main import create_app; create_app(); print('application imports and builds')"
run "backend: unit tests"     backend pytest tests/unit -q

# Integration tests need real PostgreSQL and Redis.
if backend python -c "
import sys, socket
for host, port in (('127.0.0.1', ${PG_PORT:-5433}), ('127.0.0.1', 6379)):
    s = socket.socket(); s.settimeout(1)
    try:
        s.connect((host, port))
    except OSError:
        sys.exit(1)
    finally:
        s.close()
" 2>/dev/null; then
  run "backend: integration tests" backend pytest tests/integration -q
else
  skip "backend: integration tests" "PostgreSQL or Redis is not reachable; run 'make services'"
fi

# --- Frontend ----------------------------------------------------------------
if [ -d "$FRONTEND/node_modules" ]; then
  run "frontend: lint"            frontend npm run lint
  run "frontend: typecheck"       frontend npm run typecheck
  run "frontend: tests"           frontend npm test
  run "frontend: production build" frontend npm run build
else
  skip "frontend gates" "node_modules is missing; run 'npm ci' in frontend/"
fi

# --- Repository hygiene -------------------------------------------------------
run "repo: whitespace check" git diff --check HEAD

# --- Compose ------------------------------------------------------------------
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  run "compose: development" docker compose -f docker-compose.yml config --quiet
  run "compose: production" env \
    POSTGRES_USER=x POSTGRES_PASSWORD=x POSTGRES_DB=x \
    ORIGINLENS_SECRET_KEY=x ORIGINLENS_ENCRYPTION_KEY=x ORIGINLENS_RATE_LIMIT_PEPPER=x \
    ORIGINLENS_ALLOWED_HOSTS=x ORIGINLENS_CORS_ORIGINS=x ORIGINLENS_MODEL_ID=x \
    ORIGINLENS_SMTP_HOST=x ORIGINLENS_EMAIL_FROM=x \
    docker compose -f docker-compose.prod.yml config --quiet
else
  skip "compose validation" "the docker CLI is unavailable"
fi

# --- Summary ------------------------------------------------------------------
echo
echo "══════════════════════════════════════════════════════════════════════"
echo "Summary"
echo "══════════════════════════════════════════════════════════════════════"
for item in "${PASSED[@]:-}";  do [ -n "$item" ] && echo "  PASS     $item"; done
for item in "${SKIPPED[@]:-}"; do [ -n "$item" ] && echo "  SKIP     $item"; done
for item in "${FAILED[@]:-}";  do [ -n "$item" ] && echo "  FAIL     $item"; done
echo

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "${#FAILED[@]} gate(s) failed."
  exit 1
fi
echo "All gates passed (${#PASSED[@]} run, ${#SKIPPED[@]} skipped)."
