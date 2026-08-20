# Deployment

`docker-compose.prod.yml` is a **reference to adapt**, not a turnkey
deployment. It shows the shape of a correct deployment; your orchestrator,
secret store, and reverse proxy will differ.

## Required configuration

Production start-up **fails closed**. The process refuses to start on
placeholder secrets, short secrets, debug mode, insecure cookies, `localhost` in
the host allow-list, metrics without a token, a loosened rate-limit multiplier,
or the fake detector. A misconfiguration is a startup failure, never a silently
degraded service.

| Variable | Notes |
| --- | --- |
| `ORIGINLENS_ENVIRONMENT` | `production` |
| `ORIGINLENS_SECRET_KEY` | ≥32 chars. Peppers token digests. |
| `ORIGINLENS_ENCRYPTION_KEY` | urlsafe-base64 of exactly 32 random bytes. |
| `ORIGINLENS_RATE_LIMIT_PEPPER` | ≥32 chars. Keys rate-limit identifiers. |
| `ORIGINLENS_DATABASE_URL` | `postgresql+psycopg://…` |
| `ORIGINLENS_REDIS_URL` | `redis://…` |
| `ORIGINLENS_ALLOWED_HOSTS` | Real hostnames. `localhost` is refused. |
| `ORIGINLENS_CORS_ORIGINS` | Your public origin. |
| `ORIGINLENS_DETECTOR_BACKEND` | `modernbert`. `fake` is refused. |
| `ORIGINLENS_MODEL_ID` | The checkpoint to load. |
| `ORIGINLENS_MODEL_REVISION` | **Pin a commit SHA.** A tag can be moved after review. |
| `ORIGINLENS_SMTP_*`, `ORIGINLENS_EMAIL_FROM` | Transactional mail. |
| `ORIGINLENS_COOKIE_SECURE` | `true`. |

Generate secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                      # SECRET_KEY, PEPPER
python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # ENCRYPTION_KEY
```

Supply them from your secret manager. The reference Compose file declares each
as `${VAR:?...}` so a missing value fails the deploy rather than starting on a
default.

## Deploy

### The short version

```bash
./scripts/generate-secrets.sh     # writes .env.production with fresh secrets
$EDITOR .env.production           # set your hostname, model, and SMTP details
./scripts/deploy.sh               # build, migrate, start, wait for readiness
```

`deploy.sh` refuses to run with placeholder hostnames, placeholder secrets, or
the fake detector, then validates the Compose configuration, builds, brings the
stack up, and polls readiness before reporting success.

Then create the first administrator:

```bash
COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"
$COMPOSE run --rm api python -m app.cli seed-settings
$COMPOSE run --rm api python -m app.cli create-admin --email you@example.com
```

### What that does

Migrations run as a **one-shot `migrate` container** that must complete before
the API and worker start, so a redeploy with several replicas cannot race them.

The backend images are three targets of one Dockerfile — `api`, `worker`, and
`migrate` — sharing every layer up to the entrypoint. They cannot drift in
dependencies, and none depends on another having been built first.

Images run as a non-root user, contain no compiler, and declare healthchecks.

### Building by hand

```bash
docker build --target api     -t originlens-api:$TAG     ./backend
docker build --target worker  -t originlens-worker:$TAG  ./backend
docker build --target migrate -t originlens-migrate:$TAG ./backend
docker build                  -t originlens-web:$TAG     ./frontend
```

Pass `--build-arg INCLUDE_ML=true` to bake PyTorch and Transformers in; the
production Compose file does this already.

## Network posture

The production Compose file publishes **no ports at all**. PostgreSQL and Redis
are reachable only on the internal network — exposing a database port to the
host is how a development convenience becomes an incident. The API and web
containers are reached through your reverse proxy.

### Reverse proxy

The stack publishes only `web` on `127.0.0.1:3000`. Terminate TLS in front of it.
The web tier proxies `/api/v1/*` to `api:8000` internally, so the deployment
stays same-origin and the session cookie stays host-only.

#### Caddy

Caddy obtains and renews certificates automatically, which makes it the
shortest path to a correct deployment:

```caddy
originlens.example.com {
    encode zstd gzip

    # Slightly above ORIGINLENS_MAX_UPLOAD_BYTES so the application returns its
    # own 413 envelope rather than the proxy returning a bare error page.
    request_body {
        max_size 6MB
    }

    reverse_proxy 127.0.0.1:3000 {
        # Analysis requests are CPU-bound and can take seconds.
        transport http {
            read_timeout 120s
        }
    }
}
```

#### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name originlens.example.com;

    ssl_certificate     /etc/letsencrypt/live/originlens.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/originlens.example.com/privkey.pem;

    # Slightly above ORIGINLENS_MAX_UPLOAD_BYTES.
    client_max_body_size 6m;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Analysis requests are CPU-bound and can take seconds.
        proxy_read_timeout 120s;
    }
}

server {
    listen 80;
    server_name originlens.example.com;
    return 301 https://$host$request_uri;
}
```

Whatever proxy you use, it should:

* redirect HTTP to HTTPS. The API sends HSTS itself when
  `ORIGINLENS_COOKIE_SECURE` is true.
* allow a body slightly above `ORIGINLENS_MAX_UPLOAD_BYTES`, so an oversized
  upload gets the application's JSON error envelope rather than a proxy page.
* use generous read timeouts, because inference is CPU-bound.
* **not** rewrite or strip `X-Correlation-ID`, which ties a user report to a log
  line.

#### A note on `X-Forwarded-For`

Rate limiting uses the **socket peer**, not the forwarded header, because a
spoofable header would let an attacker evade limits by rotating it. Behind a
proxy this means every client shares one identifier, and the limits become
per-deployment rather than per-client.

To use the real client address, adapt `client_identifier()` in
`app/api/deps.py` to read `X-Forwarded-For` — and only do so once you are
certain the proxy always overwrites that header rather than appending to a
client-supplied value.

## Model weights

Pre-download so the first inference does not pay the cost, and so an air-gapped
host can be seeded in advance:

```bash
make model-download
make model-smoke
```

Mount the cache as a persistent volume (the reference file does) or bake it into
the image. Without persistence, weights are re-downloaded on every deploy.

For a CPU-only deployment, install Torch from the CPU index — this drops the
`nvidia-*` wheels and roughly 2 GB of image size:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

## Migrations and rollback

```bash
alembic upgrade head        # apply
alembic current             # inspect
alembic downgrade -1        # roll back one revision
```

CI verifies that migrations apply to an empty database, that the
downgrade/upgrade round trip works, and that the schema has not drifted from the
models. **Take a backup before migrating.** A downgrade that drops a column
loses its data; only application rollback is reversible.

Deploy order: migrate first, then roll the application. Keep migrations
backward-compatible with the previous release so a rollback does not strand the
schema.

## Backups

```bash
pg_dump --format=custom --file=originlens-$(date +%F).dump "$DATABASE_URL"
```

Dumps contain **encrypted** submission envelopes, which are only useful with
`ORIGINLENS_ENCRYPTION_KEY`. Back up that key separately and at least as
carefully — losing it makes every retained submission unrecoverable. Encrypt
dumps at rest, restrict access, and retain them no longer than the retention
policy they support. Test a restore.

Redis holds rate-limit counters and queued jobs, and does not need backing up;
losing it resets counters and drops in-flight jobs, which remain `queued` in the
database.

## Retention

Schedule the sweep (cron, Celery beat, or your orchestrator). It is idempotent:

```bash
docker compose -f docker-compose.prod.yml run --rm api python -m app.cli retention-sweep
```

## Health and graceful shutdown

| Endpoint | Use |
| --- | --- |
| `/api/v1/health/live` | Liveness probe. Touches no dependency. |
| `/api/v1/health/ready` | Readiness probe. 503 when a dependency is unreachable. |
| `/api/v1/health/model` | Model readiness, separate from API readiness. |

Do not use `ready` as a liveness probe: a process with a broken database
connection is alive but not ready, and restarting it will not help.

The API drains in-flight requests for 20 seconds on `SIGTERM`. The worker uses
late acknowledgement, so a task interrupted by a shutdown is redelivered, and
its idempotency check means redelivery does not reprocess a finished job. Give
the worker a generous `stop_grace_period` (the reference uses 120 s) so an
in-flight inference can finish.

## Resource expectations

**These are estimates, not measurements.** Benchmark with your own model and
traffic before sizing.

| Component | CPU | RAM | Notes |
| --- | --- | --- | --- |
| API | 0.5–1 core | 256–512 MiB | No model loaded |
| Worker (base model, CPU) | 1–2 cores | 1.5–3 GiB | Dominated by weights plus activations |
| Web | 0.25–0.5 core | 256 MiB | Mostly static |
| PostgreSQL | 0.5–1 core | 512 MiB–1 GiB | Grows with retained text |
| Redis | 0.1 core | 128 MiB | Counters and queue only |

Scale workers horizontally, not by raising concurrency: each process holds its
own copy of the weights, so a second process costs another 1.5–3 GiB and buys
one more concurrent inference.

Disk: model weights (hundreds of MiB to a few GiB) plus the database. Retained
text is roughly the submitted size plus 29 bytes of envelope overhead per row.

## Optional metrics

`ORIGINLENS_METRICS_ENABLED` is off by default. When enabled in production a
token is required, and the endpoint should be reachable only from your
monitoring network. Metrics carry counts and timings, never content.
