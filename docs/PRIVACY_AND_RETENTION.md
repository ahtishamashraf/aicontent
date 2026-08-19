# Privacy and retention

## Principle

Submitted writing is the most sensitive thing this system handles. The design
goal is to minimise the number of places it can exist and the time it exists
there.

## Submitted text

| Submitter | Retention |
| --- | --- |
| Guest | Analysed, then discarded. Never persisted. |
| Signed-in, not opted in | Analysed, then discarded. |
| Signed-in, opted in | Encrypted at rest; deletable at any time. |

Opting in is per submission and off by default. Guests cannot opt in at all,
because there is no account to govern the data afterwards.

### Encryption

Retained text is sealed with **AES-256-GCM** from the `cryptography` library —
authenticated encryption, so tampering is detected rather than silently
decrypted. Payloads are `version ‖ nonce ‖ ciphertext`; the version prefix
exists so the algorithm or key can change without ambiguity about how an
existing row was written.

The key is `ORIGINLENS_ENCRYPTION_KEY`, urlsafe-base64 of exactly 32 random
bytes, validated at start-up. Production refuses a development placeholder.

```bash
python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

**Rotation limitation, stated plainly.** Envelopes are versioned so a new key
can be introduced, but this project does **not** yet ship a re-encryption
migration for existing rows. Rotating the key today makes previously stored text
undecryptable; the application reports a decryption failure rather than
returning corrupt data, and the affected analyses remain usable apart from their
stored text. Plan rotation accordingly, or run with retention short enough that
old envelopes age out.

## Where text is not

* **Not in logs.** Application code never passes text to the logger, and a
  redaction filter runs as defence in depth. Content-bearing keys redact through
  end of line, because their values are unbounded.
* **Not in exception traces.** Only the exception type is recorded.
* **Not in validation errors.** The default handler echoes the offending input;
  it is replaced with one that reports field names only.
* **Not in the queue.** Only an analysis id crosses Celery; the worker reads the
  text from the database.
* **Not in the admin console.** Administrators see counts, codes, and outcomes.
* **Not in feedback.** The form asks about the result and says not to paste the
  document again.
* **Not sent anywhere external.** Inference is local. There is no third-party
  model API, and the CSP forbids the browser contacting another origin.

## Identifiers

**No plaintext IP address is stored anywhere.** Rate limiting and audit records
use an HMAC-SHA256 digest of the client identifier under
`ORIGINLENS_RATE_LIMIT_PEPPER`, truncated to 128 bits. The digest is not
reversible and rotating the pepper invalidates every stored identifier.

Sessions record a coarse browser family (`Firefox`, `Chrome`, …) so a user can
recognise their own sessions. That is deliberately not a fingerprint.

## Credentials and tokens

| Item | Stored as |
| --- | --- |
| Password | Argon2id hash |
| Session token | Peppered SHA-256 digest |
| CSRF token | Peppered SHA-256 digest |
| Guest access token | Peppered SHA-256 digest |
| Verification / reset token | Peppered SHA-256 digest, single-use, expiring |

Every one of these exists in plaintext only in the client's possession. The
server cannot reconstruct a guest's result link from its database.

## Retention schedule

| Data | Default | Setting |
| --- | --- | --- |
| Guest analyses and their tokens | 24 hours | `ORIGINLENS_GUEST_RETENTION_HOURS` |
| Any analysis | 365 days | `ORIGINLENS_ANALYSIS_RETENTION_DAYS` |
| Sessions (absolute) | 14 days | `ORIGINLENS_SESSION_TTL_SECONDS` |
| Sessions (idle) | 7 days | `ORIGINLENS_SESSION_IDLE_TIMEOUT_SECONDS` |
| Verification tokens | 24 hours | — |
| Password-reset tokens | 1 hour | — |

Enforced by a sweep, not by policy:

```bash
python -m app.cli retention-sweep          # synchronous
celery -A app.tasks.worker.celery_app call originlens.retention_sweep
```

Schedule it (cron, Celery beat, or your orchestrator). It is idempotent.

## User rights

| Action | Effect |
| --- | --- |
| Delete one analysis | Removes the result, its segments, and any retained text |
| Delete all analyses | The same, for the whole history |
| Delete account | Removes the user, every analysis and segment, all retained text, all sessions and tokens, and unlinks feedback |

Deletion is immediate and uses database cascades, so nothing is left orphaned.
Feedback survives with a null user so aggregate quality signals are not lost —
it carries no identifying content.

## What is kept after an account is deleted

Only unlinked feedback rows (verdict, optional comment about the result, and
timestamp) and audit records describing administrative actions. Audit records
carry identifiers and action codes, never submitted content.

## Backups

Backups of the database contain encrypted submission envelopes. They inherit
the same key dependency described above, and should be encrypted at rest and
retained no longer than the retention policy they are meant to support.
