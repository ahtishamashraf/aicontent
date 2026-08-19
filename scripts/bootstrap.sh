#!/usr/bin/env bash
# Prepare a working development environment from a clean checkout.
#
# Idempotent: safe to re-run after pulling changes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Checking prerequisites"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v node    >/dev/null || { echo "node 20+ is required" >&2; exit 1; }
command -v npm     >/dev/null || { echo "npm is required" >&2; exit 1; }

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
case "$PY_VERSION" in
  3.11|3.12|3.13) ;;
  *) echo "Python 3.11+ is required (found $PY_VERSION)" >&2; exit 1 ;;
esac

# --- .env --------------------------------------------------------------------
if [ ! -f .env ]; then
  echo "==> Creating .env with freshly generated development secrets"
  python3 - <<'PY'
import base64, os, pathlib, secrets

template = pathlib.Path(".env.example").read_text()
replacements = {
    "ORIGINLENS_SECRET_KEY": secrets.token_urlsafe(48),
    "ORIGINLENS_RATE_LIMIT_PEPPER": secrets.token_urlsafe(48),
    "ORIGINLENS_ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
}
lines = []
for line in template.splitlines():
    key = line.split("=", 1)[0].strip()
    if key in replacements:
        lines.append(f"{key}={replacements.pop(key)}")
    else:
        lines.append(line)
pathlib.Path(".env").write_text("\n".join(lines) + "\n")
print("    .env written with generated secrets")
PY
else
  echo "==> .env already exists, leaving it alone"
fi

# --- Backend -----------------------------------------------------------------
echo "==> Setting up the backend virtualenv"
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  if command -v uv >/dev/null; then
    uv venv .venv
  else
    python3 -m venv .venv
  fi
fi

# shellcheck disable=SC1091
. .venv/bin/activate

if command -v uv >/dev/null; then
  uv pip install -e ".[dev]"
else
  pip install --upgrade pip
  pip install -e ".[dev]"
fi

echo "    backend dependencies installed"
echo "    (machine-learning extras are optional: pip install -e '.[ml]')"

# --- Frontend ----------------------------------------------------------------
echo "==> Installing frontend dependencies from the lockfile"
cd "$ROOT/frontend"
npm ci

echo
echo "Bootstrap complete."
echo
echo "Next steps:"
echo "  1. Start services:      make services      (or: docker compose up -d postgres redis mailpit)"
echo "  2. Apply migrations:    make migrate"
echo "  3. Seed settings:       make seed"
echo "  4. Create an admin:     make admin email=you@example.com"
echo "  5. Run the API:         make dev-api"
echo "  6. Run the worker:      make dev-worker"
echo "  7. Run the frontend:    make dev-web"
echo
echo "Then open http://localhost:3000 (app), http://localhost:8000/docs (API),"
echo "and http://localhost:8025 (Mailpit)."
