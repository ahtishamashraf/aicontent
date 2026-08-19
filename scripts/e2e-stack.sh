#!/usr/bin/env bash
# Boot a disposable API + frontend, run Playwright against them, then tear down.
#
# The stack uses the explicit fake detector and a throwaway database, so the
# suite never needs model weights and never touches real data.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_HOST="${E2E_PG_HOST:-127.0.0.1}"
PG_PORT="${E2E_PG_PORT:-5433}"
PG_USER="${E2E_PG_USER:-originlens}"
PG_PASS="${E2E_PG_PASSWORD:-originlens}"
DB_NAME="${E2E_DB_NAME:-originlens_e2e}"
REDIS_URL="${E2E_REDIS_URL:-redis://127.0.0.1:6379/1}"
API_PORT="${E2E_API_PORT:-8000}"
WEB_PORT="${E2E_WEB_PORT:-3000}"

export ORIGINLENS_DATABASE_URL="postgresql+psycopg://${PG_USER}:${PG_PASS}@${PG_HOST}:${PG_PORT}/${DB_NAME}"
export ORIGINLENS_REDIS_URL="$REDIS_URL"
export ORIGINLENS_DETECTOR_BACKEND=fake
export ORIGINLENS_ENVIRONMENT=development
export ORIGINLENS_COOKIE_SECURE=false
# Production-strength limits would throttle the suite; production refuses any
# value above 1.0, so this can only ever relax a non-production stack.
export ORIGINLENS_RATE_LIMIT_MULTIPLIER="${E2E_RATE_LIMIT_MULTIPLIER:-100}"

API_PID=""
WEB_PID=""
MAIL_PID=""

cleanup() {
  [ -n "$MAIL_PID" ] && kill "$MAIL_PID" 2>/dev/null
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

# Free the ports first. A server left over from an earlier run silently wins the
# bind, and the suite then tests a stale build against a stale API — which looks
# like a code regression rather than a stray process.
free_port() {
  python3 - "$1" <<'PY'
import os, signal, socket, struct, sys

port = int(sys.argv[1])

def inode_for_port(path, want):
    found = set()
    try:
        lines = open(path).read().splitlines()[1:]
    except OSError:
        return found
    for line in lines:
        parts = line.split()
        if len(parts) < 10:
            continue
        local, state, inode = parts[1], parts[3], parts[9]
        if state != "0A":          # TCP_LISTEN
            continue
        if int(local.split(":")[1], 16) == want:
            found.add(inode)
    return found

inodes = inode_for_port("/proc/net/tcp", port) | inode_for_port("/proc/net/tcp6", port)
if not inodes:
    sys.exit(0)

me = os.getpid()
for pid in filter(str.isdigit, os.listdir("/proc")):
    if int(pid) == me:
        continue
    fd_dir = f"/proc/{pid}/fd"
    try:
        fds = os.listdir(fd_dir)
    except OSError:
        continue
    for fd in fds:
        try:
            target = os.readlink(f"{fd_dir}/{fd}")
        except OSError:
            continue
        if target.startswith("socket:[") and target[8:-1] in inodes:
            try:
                os.kill(int(pid), signal.SIGTERM)
                print(f"    freed port {port} (pid {pid})")
            except OSError:
                pass
            break
PY
}

free_port "$API_PORT"
free_port "$WEB_PORT"
free_port 1025
free_port 8025
sleep 2

# Ensure PostgreSQL and Redis are up (no-op when they already are).
"$ROOT/scripts/dev-services.sh" >/dev/null 2>&1 || true

echo "==> Resetting $DB_NAME"
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE);" >/dev/null
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d postgres \
  -c "CREATE DATABASE $DB_NAME OWNER $PG_USER;" >/dev/null

cd "$ROOT/backend"
# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && . .venv/bin/activate

echo "==> Starting mail catcher (SMTP :1025, read API :8025)"
python "$ROOT/scripts/mailcatcher.py" > /tmp/e2e-mail.log 2>&1 &
MAIL_PID=$!
for _ in $(seq 1 20); do
  curl -sf -m 2 "http://127.0.0.1:8025/api/v1/messages" >/dev/null && break
  sleep 1
done

echo "==> Migrating"
alembic upgrade head 2>&1 | tail -1

echo "==> Starting API on :$API_PORT"
uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT" > /tmp/e2e-api.log 2>&1 &
API_PID=$!

for _ in $(seq 1 40); do
  curl -sf -m 2 "http://127.0.0.1:$API_PORT/api/v1/health/live" >/dev/null && break
  sleep 1
done
curl -sf -m 3 "http://127.0.0.1:$API_PORT/api/v1/health/ready" || {
  echo "API failed to become ready"; tail -20 /tmp/e2e-api.log; exit 1; }
echo

cd "$ROOT/frontend"
echo "==> Starting frontend on :$WEB_PORT"
API_INTERNAL_URL="http://127.0.0.1:$API_PORT" npm run start > /tmp/e2e-web.log 2>&1 &
WEB_PID=$!

for _ in $(seq 1 40); do
  curl -sf -m 2 "http://127.0.0.1:$WEB_PORT/" >/dev/null && break
  sleep 1
done
curl -sf -m 5 -o /dev/null "http://127.0.0.1:$WEB_PORT/api/v1/health/live" || {
  echo "Frontend proxy to the API is not working"; tail -20 /tmp/e2e-web.log; exit 1; }

echo "==> Running Playwright"
export PLAYWRIGHT_SKIP_WEBSERVER=1
export E2E_BASE_URL="http://127.0.0.1:$WEB_PORT"
# Present so the registration/verification flows run instead of skipping.
if curl -sf -m 2 "http://127.0.0.1:8025/api/v1/messages" >/dev/null; then
  export E2E_MAILPIT_URL="${E2E_MAILPIT_URL:-http://127.0.0.1:8025}"
fi
npx playwright test "$@"
STATUS=$?

echo "==> Playwright exit status: $STATUS"
exit $STATUS
