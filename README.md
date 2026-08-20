# OriginLens

Signals about how writing was produced — never a verdict on who wrote it.

OriginLens analyses English prose for stylistic patterns statistically
associated with machine generation, and reports how much weight that finding
can bear. It runs entirely on your own infrastructure: no text is sent to an
external model provider.

> **Read [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) and the in-app
> [limitations page](frontend/app/limitations/page.tsx) before relying on a
> result.** Detectors of this kind are unreliable in ways that fall hardest on
> non-native English writers. A score must never be the sole basis for a
> decision about a person.

---

## What it does

* Scores submitted text or an uploaded `.txt`, `.pdf`, or `.docx` document.
* Reports a display band, a **reliability level**, and the reasons for both —
  not a bare percentage.
* Breaks the result down by paragraph, and says plainly when a paragraph is too
  short to score rather than inventing a number for it.
* Shows neutral text statistics as context, kept explicitly separate from the
  classifier.
* Returns `Insufficient text` below the minimum word count and
  `Unsupported language` for anything that is not English, instead of guessing.

## What it deliberately does not do

* It does not claim to detect authorship.
* It does not publish an accuracy figure, because none has been measured on a
  dataset large or representative enough to support the claim.
* It does not call its score a probability. The active calibration is the
  identity mapping and its version string says so.
* It never substitutes a fabricated result when the model is unavailable — an
  outage surfaces as an error.

---

## Quick start

Requirements: Python 3.11+, Node 20+, and either Docker or local PostgreSQL 16
and Redis.

```bash
git clone <this repository> && cd aicontent

# 1. Install everything and generate development secrets into .env
./scripts/bootstrap.sh

# 2. Start PostgreSQL, Redis, and Mailpit
docker compose up -d postgres redis mailpit
#   …or, without a Docker daemon:
make services

# 3. Prepare the database
make migrate
make seed
make admin email=you@example.com

# 4. Run the three processes, each in its own terminal
make dev-api
make dev-worker
make dev-web
```

Then open:

| What | Where |
| --- | --- |
| Application | <http://localhost:3000> |
| API docs (development only) | <http://localhost:8000/docs> |
| Liveness / readiness | <http://localhost:8000/api/v1/health/live>, `…/ready` |
| Model readiness | <http://localhost:8000/api/v1/health/model> |
| Mailpit | <http://localhost:8025> |

### Everything in containers

```bash
make up      # builds, migrates, and starts the whole stack
make logs
make down
```

`docker compose up` runs migrations as a one-shot container that must finish
before the API and worker start, so there is nothing to remember and nothing to
race.

---

## Deploying to production

```bash
./scripts/generate-secrets.sh    # writes .env.production with fresh secrets
$EDITOR .env.production          # set your hostname, model, and SMTP details
./scripts/deploy.sh              # build, migrate, start, wait for readiness
```

`deploy.sh` refuses to proceed with placeholder hostnames, placeholder secrets,
or the fake detector; validates the Compose configuration; builds; brings the
stack up; and polls readiness before reporting success.

Then:

```bash
COMPOSE="docker compose --env-file .env.production -f docker-compose.prod.yml"
$COMPOSE run --rm api python -m app.cli seed-settings
$COMPOSE run --rm api python -m app.cli create-admin --email you@example.com
```

The production stack publishes **only** the web tier, and only on loopback —
PostgreSQL and Redis are unreachable from outside the Compose network. Point a
TLS-terminating reverse proxy at `127.0.0.1:3000`; worked nginx and Caddy
configurations are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

Back up `ORIGINLENS_ENCRYPTION_KEY` separately. Losing it makes every retained
submission unrecoverable.

---

## Quality gates

```bash
make check         # format, lint, types, tests, build, compose validation
make e2e           # Playwright against a disposable stack with the fake detector
make model-smoke   # load the configured real model and run one inference
git diff --check   # whitespace
```

`make check` continues past a failing gate so one run reports every problem,
then prints a pass/skip/fail summary and exits non-zero if anything failed.

---

## The detector backends

`ORIGINLENS_DETECTOR_BACKEND` selects one of two providers.

**`fake`** is a deterministic test double. It performs no machine learning; its
output is a stable hash and is meaningless as a classification. It exists so the
API, worker, and end-to-end tests can exercise the full lifecycle without model
weights. It is named `fake` everywhere it appears — in settings, in health
output, and in the provenance recorded on every result — and **the settings
layer refuses to start a production process that selects it.**

**`modernbert`** loads a real sequence-classification checkpoint. The model ID
and revision are configuration. The provider resolves which output index means
"AI" from the checkpoint's own `id2label`/`label2id` rather than assuming index
order, and refuses to load a checkpoint whose labels are generic, ambiguous, or
internally contradictory — guessing would invert every prediction on half of all
checkpoints. Weights load once per process, run on CPU by default, and use CUDA
only when configured and actually present.

```bash
make model-download   # pre-populate the cache
make model-smoke      # verify it loads and infers
make evaluate         # metrics over the checked-in fixture set
```

Pin `ORIGINLENS_MODEL_REVISION` to a commit SHA in production: a tag can be
moved by the publisher after you have reviewed it.

---

## Repository layout

```
backend/
  app/
    api/v1/       HTTP routes (health, auth, analyses, feedback, admin)
    auth/         opaque sessions, CSRF, single-use email tokens
    core/         settings, security, crypto, logging, rate limiting, errors
    db/           typed SQLAlchemy models and session management
    services/     analysis lifecycle, document extraction, email, audit
    tasks/        Celery application and background tasks
    cli/          administrative commands
  detection/      the domain: normalization, segmentation, scoring, diagnostics
  alembic/        migrations
  tests/          unit, integration, and fixture builders
frontend/
  app/            Next.js App Router pages
  components/     UI, analyzer, result, dashboard, admin
  lib/            API client, types, formatting
  tests/          Vitest + React Testing Library
  e2e/            Playwright specs
scripts/          bootstrap, checks, services, model, evaluation, E2E stack
docs/             architecture, API, data model, methodology, threat model, status
```

---

## Documentation

| Document | What it covers |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Processes, request flow, and why the pieces are split as they are |
| [`docs/API.md`](docs/API.md) | Every endpoint, its contract, and its error envelope |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Tables, relationships, and what is deliberately not stored |
| [`docs/DETECTION_METHODOLOGY.md`](docs/DETECTION_METHODOLOGY.md) | How a score is produced, end to end |
| [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) | Intended use, known failure modes, and prohibited uses |
| [`docs/PRIVACY_AND_RETENTION.md`](docs/PRIVACY_AND_RETENTION.md) | What is stored, encrypted, and deleted, and when |
| [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md) | Threats, controls, and residual risk |
| [`docs/TESTING.md`](docs/TESTING.md) | What is tested at each layer and how to run it |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Production configuration, migrations, backups, and rollback |
| [`docs/STATUS.md`](docs/STATUS.md) | Current state and genuine residual limitations |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Design decisions and the reasoning behind them |

## Licence

See [`LICENSE`](LICENSE).
