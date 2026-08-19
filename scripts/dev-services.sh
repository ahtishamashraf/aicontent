#!/usr/bin/env bash
# Start PostgreSQL and Redis locally, for environments without a Docker daemon.
#
# Docker Compose is the documented path (docker-compose.yml). This script is the
# fallback used by CI images and sandboxes where the daemon is unavailable, so
# that migrations, integration tests, and E2E can still run against the real
# databases rather than being skipped.
set -uo pipefail

PG_VERSION="${PG_VERSION:-16}"
PG_BIN="/usr/lib/postgresql/${PG_VERSION}/bin"
PGDATA="${PGDATA:-/var/lib/postgresql/originlens}"
PG_PORT="${PG_PORT:-5433}"
DB_USER="${DB_USER:-originlens}"
DB_PASSWORD="${DB_PASSWORD:-originlens}"

if [ ! -x "$PG_BIN/pg_ctl" ]; then
  echo "PostgreSQL $PG_VERSION is not installed at $PG_BIN" >&2
  exit 1
fi

# --- PostgreSQL --------------------------------------------------------------
mkdir -p "$PGDATA"
chown -R postgres:postgres "$PGDATA"
chmod 700 "$PGDATA"

if [ ! -f "$PGDATA/PG_VERSION" ]; then
  echo "==> initdb"
  su postgres -c "$PG_BIN/initdb -D $PGDATA -A trust -E UTF8" >/dev/null
fi

if ! su postgres -c "$PG_BIN/pg_isready -h /tmp -p $PG_PORT" >/dev/null 2>&1; then
  echo "==> Starting PostgreSQL on :$PG_PORT"
  su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -o '-p $PG_PORT -k /tmp' -l $PGDATA/server.log start" >/dev/null
  for _ in $(seq 1 30); do
    su postgres -c "$PG_BIN/pg_isready -h /tmp -p $PG_PORT" >/dev/null 2>&1 && break
    sleep 1
  done
fi

psql_super() { su postgres -c "$PG_BIN/psql -h /tmp -p $PG_PORT -d postgres -tAc \"$1\"" 2>/dev/null; }

if [ "$(psql_super "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'")" != "1" ]; then
  echo "==> Creating role $DB_USER"
  psql_super "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD' SUPERUSER" >/dev/null
fi

for db in originlens originlens_test; do
  if [ "$(psql_super "SELECT 1 FROM pg_database WHERE datname='$db'")" != "1" ]; then
    echo "==> Creating database $db"
    psql_super "CREATE DATABASE $db OWNER $DB_USER" >/dev/null
  fi
done

# --- Redis -------------------------------------------------------------------
if ! redis-cli ping >/dev/null 2>&1; then
  echo "==> Starting Redis on :6379"
  redis-server --port 6379 --daemonize yes --save '' --appendonly no >/dev/null
  for _ in $(seq 1 20); do
    redis-cli ping >/dev/null 2>&1 && break
    sleep 1
  done
fi

echo "PostgreSQL: $(su postgres -c "$PG_BIN/pg_isready -h /tmp -p $PG_PORT" 2>&1)"
echo "Redis:      $(redis-cli ping 2>&1)"
