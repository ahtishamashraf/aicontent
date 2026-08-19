# Testing

## Layers

| Layer | Location | What it covers |
| --- | --- | --- |
| Backend unit | `backend/tests/unit/` | Settings validation, normalization, language routing, segmentation, aggregation, calibration, reliability, diagnostics, document security, provider contracts |
| Backend integration | `backend/tests/integration/` | Real PostgreSQL and Redis: auth lifecycle, CSRF, sessions, authorization boundaries, guest tokens, analysis lifecycle, uploads, admin, rate limiting, content safety |
| Real provider | `backend/tests/integration/test_real_provider.py` | Actual PyTorch and Transformers against a locally-built checkpoint |
| Frontend component | `frontend/tests/` | Vitest and React Testing Library |
| End-to-end | `frontend/e2e/` | Playwright against a full stack with the fake detector |

## Running

```bash
make check              # every gate, with a pass/skip/fail summary
make test               # backend unit + frontend component
make test-integration   # needs PostgreSQL and Redis
make e2e                # boots a disposable stack and runs Playwright
make model-smoke        # the configured real model
```

`make check` continues past a failing gate so one run reports every problem, and
exits non-zero if anything failed.

## Requirements

Integration tests need PostgreSQL and Redis. With Docker:

```bash
docker compose up -d postgres redis
```

Without a Docker daemon:

```bash
make services     # starts PostgreSQL 16 and Redis natively
```

Integration tests create a **disposable database and migrate it with Alembic**,
not with `metadata.create_all`. That way the tests exercise the same DDL a
deployment applies, and a migration that drifts from the models fails the suite.

## The fake detector

Integration and end-to-end tests run with `ORIGINLENS_DETECTOR_BACKEND=fake`, a
deterministic test double that performs no machine learning. It exists so the
full lifecycle can be exercised without model weights. It is named `fake`
everywhere it appears, and production refuses it.

## The real provider

`test_real_provider.py` builds a tiny, randomly-initialised
sequence-classification checkpoint on disk and exercises the genuine provider:
loading, label resolution, tokenizer windowing, inference, finiteness, and
provenance. No network access is needed.

The scores such a model returns are meaningless, so nothing asserts a
classification. What is asserted is that inference runs, output is finite and
in range, windows are token-weighted, CUDA is refused rather than silently
downgraded when unavailable, and a checkpoint with generic `LABEL_0`/`LABEL_1`
labels is rejected at load.

This suite has already earned its place twice. It caught a missing batch axis
that would have made every real inference raise `ValueError`, and it caught two
separate Transformers 5 API removals. Neither was reachable by a unit test with
a mocked tokenizer.

## Model smoke

`make model-smoke` is separate and exercises the **configured** model. It
asserts that the model loads, its label mapping is interpretable, and inference
is finite and well-formed. It deliberately **does not** assert a classification
for a sample sentence: a detector that returns "AI" for one crafted string
proves nothing, and encoding that expectation would turn a green test into false
comfort. The observed score is printed for the operator to judge.

## End-to-end

`scripts/e2e-stack.sh` frees its ports, ensures PostgreSQL and Redis are up,
resets a throwaway database, migrates it, starts a mail catcher, the API, and
the frontend, runs Playwright, and tears everything down.

Rate limits are scaled by `ORIGINLENS_RATE_LIMIT_MULTIPLIER` for the test stack.
Production refuses any value above 1.0, so this can only relax a non-production
deployment. Without it the suite exhausts the five-per-hour guest limit and
fails for the wrong reason.

Covered on both desktop and mobile viewports:

1. Guest submits text, sees the result, opens a paragraph, exports JSON.
2. Short text is refused client-side and reported `Insufficient text` by the API.
3. Non-English text is reported `Unsupported language` with no score.
4. Registration, email verification, login, analysis, history, deletion.
5. One user cannot open another user's analysis.
6. A guest result cannot be opened without its token.
7. An ordinary user cannot reach admin pages or the admin API.
8. The printable result keeps its disclaimer and hides the navigation.
9. No horizontal overflow at 320 px on the analyzer and result routes.
10. The primary guest flow is completable with the keyboard alone.

Email verification uses a Mailpit-compatible read API. Docker Compose runs the
real Mailpit; `scripts/mailcatcher.py` is the fallback where no daemon is
available, so these flows run rather than being skipped.

## Zero tests is a failure

The frontend test script sets `passWithNoTests=false`, so a run that discovers
nothing exits non-zero. A green command with zero tests is not a pass, and CI
would otherwise report success for a deleted suite.

## Fixtures

No real submitted user writing appears in any fixture, and none ever should.

* Document fixtures — including the hostile ones — are **synthesised in code**
  (`backend/tests/fixtures/build_fixtures.py`) rather than committed as
  binaries, so every one is auditable and the repository carries no opaque blobs.
* Evaluation fixtures are public-domain (pre-1900) or written for this
  repository, with provenance recorded in
  `backend/tests/fixtures/evaluation/README.md`.
* Playwright traces and screenshots can contain submitted text, so they are
  captured only on failure, retained briefly, and must be reviewed before
  sharing.
