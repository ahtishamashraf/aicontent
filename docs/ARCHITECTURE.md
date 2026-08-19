# Architecture

## Processes

OriginLens runs as four cooperating processes plus two data stores.

```
        browser
           │  same-origin HTTPS
           ▼
  ┌─────────────────┐
  │  web (Next.js)  │  renders the UI; proxies /api/v1/* to the API so the
  │                 │  session cookie stays host-only and there is no CORS
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐        ┌──────────────┐
  │   api (FastAPI) │───────▶│  PostgreSQL  │  users, sessions, analyses,
  │                 │        │              │  segments, feedback, audit
  └────┬───────┬────┘        └──────▲───────┘
       │       │                    │
       │       ▼                    │
       │  ┌──────────┐              │
       │  │  Redis   │  rate limits, Celery broker
       │  └────┬─────┘              │
       │       │                    │
       ▼       ▼                    │
  ┌─────────────────┐               │
  │ worker (Celery) │───────────────┘
  │  loads the model│
  └─────────────────┘
```

### Why the split

**The web tier proxies the API rather than calling it cross-origin.** A
same-origin deployment means the session cookie can be host-only and
`SameSite=Lax`, and no CORS preflight is involved in normal use. Cross-origin
would require loosening both.

**The worker is separate from the API.** A transformer checkpoint is hundreds of
megabytes of resident memory and an inference is CPU-bound for seconds. Running
that inside the request-handling process would let one submission block
unrelated requests, and would multiply the weights by the number of API workers.

**Only an analysis id crosses the queue.** The worker reads the submitted text
from the database, so Redis never holds document content and neither does any
queue metadata or task result.

## Request flow: submitting text

1. The browser POSTs to `/api/v1/analyses/text` on its own origin; Next rewrites
   it to the API.
2. Middleware assigns a correlation ID, which is echoed in the response header
   and appears in every log line for the request.
3. The rate limiter consumes one unit against a keyed digest of the client
   identifier — never a stored IP address.
4. A row is created in `queued`. Guest submissions also get a random access
   token whose digest alone is persisted.
5. The pipeline runs: size and shape validation, normalization, language
   routing, length gating, token-window scoring, aggregation, calibration,
   reliability assessment, paragraph attribution, diagnostics.
6. The row moves to `completed` (or `failed` with a bounded code) and its
   segments are written.
7. The response carries the result, the disclaimers, and the provenance.

The Celery path exists for the same lifecycle when work is deferred, and shares
`app/services/analysis.py` with the request path so the state machine has one
implementation. Transitions are validated: a terminal analysis can never be
reopened, and a redelivered task returns without reprocessing.

## The detection domain

`backend/detection/` holds the domain logic and depends on no HTTP or database
code, so it can be exercised directly by unit tests.

| Module | Responsibility |
| --- | --- |
| `normalization` | display vs. analysis copies; integrity warnings |
| `language` | offline English detection with a documented threshold |
| `segmentation` | paragraphs, sentences, and token windows |
| `aggregation` | token-weighted combination and disagreement |
| `calibration` | versioned thresholds, bands, and reliability rules |
| `diagnostics` | neutral deterministic statistics |
| `engines/` | the provider protocol, the fake double, the real model |
| `registry` | one loaded provider per process, with no silent fallback |
| `pipeline` | orchestration of all of the above |

### The provider boundary

`DetectorProvider` is a protocol with `load()`, `score_text()`, and
`metadata()`. Two implementations exist. The registry constructs and loads one
per process and caches it; a load failure is recorded and re-raised on every
subsequent call. **There is no fallback path from the real provider to the
fake one** — a fabricated score is worse than an honest error.

## Security architecture

| Concern | Where it lives |
| --- | --- |
| Fail-closed configuration | `app/core/config.py` — production refuses placeholder secrets, debug mode, insecure cookies, the fake detector, and loosened rate limits |
| Password hashing | `app/core/security.py` — Argon2id |
| Opaque tokens | `app/core/security.py` — peppered SHA-256; only digests are stored |
| Encryption at rest | `app/core/crypto.py` — AES-256-GCM with a version prefix |
| Sessions | `app/auth/sessions.py` — server-side, rotating, revocable |
| CSRF | `app/auth/csrf.py` — double-submit, constant-time comparison |
| Rate limiting | `app/core/ratelimit.py` — keyed digests, fail-closed on auth paths |
| Content-safe logging | `app/core/logging.py` — JSON with a redaction filter |
| Error envelopes | `app/core/errors.py` — curated messages, never exception text |
| Document safety | `app/services/documents/` — signatures, archive inspection, bounds |

Authorization is enforced inside the query rather than by comparing fields after
a lookup, so an IDOR probe receives the same 404 as a genuinely missing row.

## Frontend architecture

The App Router serves mostly static pages; only `/result/[id]` is dynamic.
Client components handle the analyzer, result, dashboard, and admin console.

`ConfigProvider` fetches `/api/v1/config` once and supplies limits, band
thresholds, and disclaimers to the whole tree. Nothing is duplicated in the
client, so the values shown always match the ones the server enforces.

`RequireAuth` is a convenience so a signed-out visitor sees a prompt instead of
an error. It is not the access control: every protected route re-checks the
session and role server-side on each request.
