# OriginLens developer commands.
#
# Every target here is expected to work from a clean checkout after
# `make bootstrap`. See README.md for the full walkthrough.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
.PHONY: bootstrap
bootstrap: ## Create the venv, install all dependencies, prepare .env
	./scripts/bootstrap.sh

.PHONY: lock
lock: ## Regenerate the Python lockfiles from the current venv
	@cd $(BACKEND) && . .venv/bin/activate && \
	  ML='^(torch|transformers|tokenizers|safetensors|huggingface-hub|regex|numpy|filelock|fsspec|sympy|networkx|mpmath|triton|setuptools)==|^nvidia-'; \
	  { head -8 requirements.lock; uv pip freeze | grep -viE "$$ML" | grep -v '^-e file:' | sort; } > requirements.lock.new && \
	  mv requirements.lock.new requirements.lock && \
	  { head -9 requirements-ml.lock; uv pip freeze | grep -iE "$$ML" | grep -v '^setuptools' | sort; } > requirements-ml.lock.new && \
	  mv requirements-ml.lock.new requirements-ml.lock
	@echo "Lockfiles regenerated."

.PHONY: services
services: ## Start PostgreSQL and Redis locally (fallback when Docker is unavailable)
	./scripts/dev-services.sh

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
.PHONY: migrate
migrate: ## Apply all migrations
	cd $(BACKEND) && . .venv/bin/activate && alembic upgrade head

.PHONY: migrate-down
migrate-down: ## Roll back the most recent migration
	cd $(BACKEND) && . .venv/bin/activate && alembic downgrade -1

.PHONY: migration
migration: ## Autogenerate a migration: make migration m="add widgets"
	cd $(BACKEND) && . .venv/bin/activate && alembic revision --autogenerate -m "$(m)"

.PHONY: admin
admin: ## Create an administrator: make admin email=you@example.com
	cd $(BACKEND) && . .venv/bin/activate && python -m app.cli create-admin --email "$(email)"

.PHONY: seed
seed: ## Insert default system settings
	cd $(BACKEND) && . .venv/bin/activate && python -m app.cli seed-settings

# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
.PHONY: dev-api
dev-api: ## Run the API with reload
	cd $(BACKEND) && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

.PHONY: dev-worker
dev-worker: ## Run the Celery worker
	cd $(BACKEND) && . .venv/bin/activate && \
	  celery -A app.tasks.worker.celery_app worker --loglevel=INFO --concurrency=1

.PHONY: dev-web
dev-web: ## Run the frontend dev server
	cd $(FRONTEND) && npm run dev

.PHONY: up
up: ## Start the full development stack (builds, migrates, runs)
	docker compose up --build -d
	@echo
	@echo "App:      http://localhost:3000"
	@echo "API docs: http://localhost:8000/docs"
	@echo "Mailpit:  http://localhost:8025"

.PHONY: down
down: ## Stop the development stack
	docker compose down

.PHONY: logs
logs: ## Follow logs from the development stack
	docker compose logs -f --tail 100

.PHONY: secrets
secrets: ## Generate .env.production with fresh secrets
	./scripts/generate-secrets.sh

.PHONY: deploy
deploy: ## Build, migrate, and start the production stack
	./scripts/deploy.sh

# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------
.PHONY: check
check: ## Run every quality gate (formatting, lint, types, tests, build)
	./scripts/check.sh

.PHONY: format
format: ## Apply formatters
	cd $(BACKEND) && . .venv/bin/activate && ruff format . && ruff check . --fix

.PHONY: lint
lint: ## Lint backend and frontend
	cd $(BACKEND) && . .venv/bin/activate && ruff check .
	cd $(FRONTEND) && npm run lint

.PHONY: typecheck
typecheck: ## Type-check backend and frontend
	cd $(BACKEND) && . .venv/bin/activate && mypy app detection
	cd $(FRONTEND) && npm run typecheck

.PHONY: test
test: ## Run backend unit tests and frontend component tests
	cd $(BACKEND) && . .venv/bin/activate && pytest tests/unit -q
	cd $(FRONTEND) && npm test

.PHONY: test-integration
test-integration: ## Run backend integration tests (needs PostgreSQL and Redis)
	cd $(BACKEND) && . .venv/bin/activate && pytest tests/integration -q

.PHONY: e2e
e2e: ## Run Playwright end-to-end tests against a disposable stack
	./scripts/e2e-stack.sh

.PHONY: model-smoke
model-smoke: ## Load the configured real model and run one inference
	cd $(BACKEND) && . .venv/bin/activate && python ../scripts/model_smoke.py

.PHONY: model-download
model-download: ## Pre-download the configured model into the local cache
	cd $(BACKEND) && . .venv/bin/activate && python ../scripts/download_model.py

.PHONY: evaluate
evaluate: ## Evaluate the detector against the checked-in fixture set
	cd $(BACKEND) && . .venv/bin/activate && python ../scripts/evaluate.py

.PHONY: compose-validate
compose-validate: ## Validate both Compose files
	docker compose -f docker-compose.yml config >/dev/null && echo "docker-compose.yml OK"
	@POSTGRES_USER=x POSTGRES_PASSWORD=x POSTGRES_DB=x ORIGINLENS_SECRET_KEY=x \
	 ORIGINLENS_ENCRYPTION_KEY=x ORIGINLENS_RATE_LIMIT_PEPPER=x ORIGINLENS_ALLOWED_HOSTS=x \
	 ORIGINLENS_CORS_ORIGINS=x ORIGINLENS_MODEL_ID=x ORIGINLENS_SMTP_HOST=x \
	 ORIGINLENS_EMAIL_FROM=x \
	 docker compose -f docker-compose.prod.yml config >/dev/null && echo "docker-compose.prod.yml OK"

.PHONY: clean
clean: ## Remove build artefacts and caches
	rm -rf $(FRONTEND)/.next $(FRONTEND)/test-results $(FRONTEND)/playwright-report
	find $(BACKEND) -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.mypy_cache $(BACKEND)/.ruff_cache
