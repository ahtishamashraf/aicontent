# API

All routes live under `/api/v1`. In the default same-origin deployment the
frontend proxies this prefix to the API, so the browser only ever talks to its
own origin.

Interactive documentation is served at `/docs` in non-production environments
and is disabled in production, along with `/openapi.json`.

## Conventions

**Authentication** is a server-side session addressed by an opaque cookie. Only
the token's digest is stored, so a database disclosure yields no usable
sessions.

**CSRF**: every state-changing request must echo the readable
`originlens_csrf` cookie in an `X-CSRF-Token` header. `GET`, `HEAD`, and
`OPTIONS` are exempt.

**Errors** always take this shape, with no stack trace, SQL, or fragment of
submitted content:

```json
{
  "error": {
    "code": "rate_limited",
    "message": "Too many requests. Please wait before trying again.",
    "correlation_id": "b2c1a0f4-...",
    "retry_after": 900
  }
}
```

The `correlation_id` is also returned in the `X-Correlation-ID` response header
and appears in the server log line for the request, so a user-reported problem
can be located without asking them to resend their document.

| Code | Status | Meaning |
| --- | --- | --- |
| `validation_failed` | 422 | Input failed validation. Reports field names only, never values. |
| `authentication_required` | 401 | No usable session. |
| `invalid_credentials` | 401 | Deliberately generic; see *Enumeration* below. |
| `permission_denied` | 403 | Authenticated but not permitted. |
| `csrf_failed` | 403 | Missing or invalid CSRF token. |
| `not_found` | 404 | Absent, or not yours — the two are indistinguishable by design. |
| `conflict` | 409 | Invalid state transition. |
| `payload_too_large` | 413 | Over the configured size limit. |
| `document_rejected` | 400 | The upload could not be processed safely. |
| `rate_limited` | 429 | Limit exhausted. Carries `Retry-After`. |
| `analysis_unavailable` | 503 | The detector could not run. No result is fabricated. |
| `internal_error` | 500 | Unexpected failure. |

**Enumeration posture.** Registration, forgotten-password, and
verification-resend return the same acknowledgement whether or not the address
exists, and spend comparable work so timing does not distinguish them. Login
returns one generic error for unknown addresses, wrong passwords, and
unverified accounts alike. Suspension *is* reported explicitly, because the
person already knows their account exists and needs to know why they cannot get
in.

---

## Health and configuration

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| `GET` | `/health/live` | — | The process is running. Touches no dependency. |
| `GET` | `/health/ready` | — | Reports database and Redis reachability. 503 when degraded. |
| `GET` | `/health/model` | — | Detector readiness, reported separately from API readiness. |
| `GET` | `/config` | — | Limits, band thresholds, disclaimers, allowed extensions. |

Liveness and readiness answer different questions. A process with a broken
database connection is alive but not ready; restarting it would not help, so
the two must not be conflated. Model readiness is separate again, because the
API can serve history and account routes while a worker's model is still
loading.

`GET /config` is the single source of truth for limits and bands. The frontend
reads it rather than duplicating the values.

---

## Authentication

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | — | 202. Generic acknowledgement. Rate limited. |
| `POST` | `/auth/verify` | — | Consumes a single-use, expiring token. |
| `POST` | `/auth/verify/resend` | — | Generic acknowledgement. Rate limited. |
| `POST` | `/auth/login` | — | Issues a fresh session. Rate limited, **fail-closed**. |
| `POST` | `/auth/logout` | session | Revokes the session server-side. |
| `GET` | `/auth/session` | optional | 200 with `{"user": null}` when anonymous. |
| `POST` | `/auth/password/forgot` | — | Generic acknowledgement. Rate limited. |
| `POST` | `/auth/password/reset` | — | Single-use token; revokes every session. |
| `POST` | `/auth/password/change` | session | Rotates the session, revokes the others. |
| `DELETE` | `/auth/account` | session | Deletes the account and all dependent records. |

`GET /auth/session` returns 200 with a null user rather than 401. Not being
signed in is a valid answer to "who am I", and a 401 on every page load fills
the browser console with errors that then hide real ones.

Login fails **closed** under rate limiting: if Redis is unreachable the request
is refused rather than allowed, so an outage cannot become an unlimited
credential-stuffing window. Ordinary traffic fails open.

---

## Analysis

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| `POST` | `/analyses/text` | optional | Submit text. Guests receive a one-time access token. |
| `POST` | `/analyses/document` | optional | Multipart `.txt`, `.pdf`, or `.docx` upload. |
| `GET` | `/analyses/{id}` | owner or `?token=` | Full result. |
| `GET` | `/analyses/{id}/status` | owner or `?token=` | Poll job state. |
| `GET` | `/analyses` | session | The caller's own analyses, paginated and filterable. |
| `DELETE` | `/analyses/{id}` | owner | Deletes the analysis and any retained text. |
| `DELETE` | `/analyses` | session | Deletes the caller's entire history. |
| `POST` | `/analyses/{id}/feedback` | owner or `?token=` | Feedback on the result. |

### The result payload

```jsonc
{
  "id": "…", "status": "completed", "source": "text",
  "label": "Uncertain or mixed signals",
  "public_score": 52,          // 0–100, or null
  "raw_model_score": 0.5231,   // stored separately from the public score
  "reliability": "moderate",   // insufficient | low | moderate | normal
  "reliability_reasons": ["Sections of the text scored somewhat differently…"],
  "counts": { "words": 412, "characters": 2480, "paragraphs": 5 },
  "detected_language": "en", "language_confidence": 0.99,
  "window_stability": 0.19,
  "segments": [ { "id": "p-000", "public_score": 61, "too_short": false, … } ],
  "integrity_warnings": [ { "code": "invisible_characters", "message": "…" } ],
  "diagnostics": { … },
  "model_metadata": { "backend": "modernbert", "model_id": "…", "revision": "…",
                      "device": "cpu", "torch_version": "…", … },
  "calibration_version": "identity-1.0.0",
  "detector_version": "1.0.0",
  "guest_token": "…",          // only on creation, only for guests
  "disclaimers": ["…"]
}
```

`public_score` is `null` — not `0` — when nothing was scored. `label` then
carries the reason (`Insufficient text`, `Unsupported language`). A paragraph
too short to judge has `public_score: null` and `too_short: true`, because a
number there would imply a precision the analyser does not have.

`raw_model_score` and `public_score` are separate fields so calibration can
change without losing the model's actual output.

### Guest access

A guest result is addressed by a random token returned once at creation. The
server stores only its digest, so the link cannot be reconstructed from the
database. Requesting the result without the token returns **404**, identical to
a genuinely missing analysis. Guest results expire after
`ORIGINLENS_GUEST_RETENTION_HOURS` and are removed by the retention sweep.

---

## Administration

Every route below re-checks the administrator role server-side on each request.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/admin/users` | Paginated; `search` is bound as a parameter, never interpolated. |
| `POST` | `/admin/users/{id}/suspend` | Requires a reason; revokes the target's sessions immediately. |
| `POST` | `/admin/users/{id}/reactivate` | Returns a suspended account to active. |
| `GET` | `/admin/stats` | Aggregate counts only. |
| `GET` | `/admin/feedback` | Reviewer comments only — never the analysed document. |
| `GET` | `/admin/settings` | Typed system settings. |
| `PUT` | `/admin/settings/{key}` | Rejects a value of the wrong type. |
| `GET` | `/admin/audit-logs` | Administrative and security events. |
| `GET` | `/admin/health/model` | Detailed model health, including load errors. |

No administrator route exposes submitted text. An administrator can see that an
analysis exists, its counts, and its outcome — not its content.

---

## Limits

Limits are configuration; `GET /config` reports the values in force.

| Limit | Default |
| --- | --- |
| Minimum words | 80 |
| Low-reliability threshold | 150 |
| Maximum words / characters | 10,000 / 50,000 |
| Upload size | 5 MiB |
| Guest analyses | 5 per hour |
| Authenticated analyses | 60 per hour |
| Login attempts | 10 per 15 minutes |
| Registration, password reset, verification resend | 5 per hour |
| Feedback | 20 per hour |

Rate-limit counters key on an HMAC-SHA256 digest of the client identifier under
a server-side pepper. A plaintext IP address is never stored, and rotating the
pepper invalidates every stored identifier.
