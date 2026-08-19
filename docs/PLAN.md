# Plan and delivery record

This records what was built, in what order, and what remains. It describes the
state of the repository rather than an aspiration; `STATUS.md` carries the
current verification results.

## Delivered

| Stage | Outcome |
| --- | --- |
| 1. Foundation | Fail-closed settings, Argon2id, peppered token digests, AES-256-GCM envelopes, content-safe JSON logging, typed models, initial migration verified against PostgreSQL 16 |
| 2. Detection domain | Normalization with integrity warnings, offline language routing, token-window segmentation, weighted aggregation with disagreement, versioned calibration, deterministic diagnostics, provider protocol with fake and real backends |
| 3. API | Sessions, CSRF, enumeration-resistant auth, analysis lifecycle, secure document extraction, feedback, admin, uniform error envelopes |
| 4. Worker and tooling | Celery with bounded concurrency and idempotent tasks, admin CLI, model download and smoke scripts, evaluation harness with withheld metrics |
| 5. Frontend | Next.js App Router, analyzer, result experience, dashboard, account, admin console, accessibility and print styles |
| 6. Tests | Backend unit and integration against real PostgreSQL and Redis, real-provider suite, Vitest components, Playwright on desktop and mobile |
| 7. Infrastructure | Multi-stage Dockerfiles, development and production Compose, CI, security workflow, Dependabot, developer scripts |
| 8. Documentation | Architecture, API, data model, methodology, model card, privacy, threat model, testing, deployment, decisions |

## Deliberately not built

* **A calibrated score.** Requires a labelled dataset this project does not
  have. Shipping the identity mapping and saying so is the honest alternative.
* **A published accuracy figure.** Same reason.
* **Diagnostic-weighted scoring.** No validated weighting exists; inventing one
  would be pseudo-science.
* **Non-English support.** Would require validation per language.
* **OCR.** Out of scope; image-only PDFs are refused with a clear explanation.

## Known gaps

Tracked in [`STATUS.md`](STATUS.md), which records what has been verified, what
has not, and why.
