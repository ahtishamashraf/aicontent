# Threat model

Assets worth protecting, in order: **submitted text**, account credentials and
sessions, and service availability.

The submitted text is the crown jewel. Someone analysing a draft resignation
letter, a legal filing, or a student's essay has handed over something they
would not want disclosed, and the system is built so that the number of places
it can leak from is as close to zero as the design allows.

## Adversaries

| Adversary | Capability | Motivation |
| --- | --- | --- |
| Opportunistic attacker | Public endpoints, automation | Credential stuffing, free compute, defacement |
| Malicious submitter | Crafted text and documents | Denial of service, evasion, code execution via a parser |
| Authenticated user | A valid account | Reading another user's analyses, privilege escalation |
| Curious insider | Admin console, logs, metrics | Reading submitted content |
| Network observer | Traffic between tiers | Session theft, content interception |
| Supply-chain attacker | A dependency or model checkpoint | Code execution in the worker |

## Threats and controls

### Credential stuffing and brute force
Argon2id hashing with interactive parameters. Login is rate limited (10 per 15
minutes) and **fails closed**: if Redis is unreachable the attempt is refused,
so an outage cannot become an unlimited guessing window. Failed attempts are
counted per user.

### Account enumeration
Registration, forgotten-password, and verification-resend return one
acknowledgement regardless of whether the address exists, and spend comparable
work so response time does not distinguish them. Login returns one generic error
for unknown addresses, wrong passwords, and unverified accounts alike.
*Residual:* a determined attacker may still infer existence from side channels
such as delivery timing outside our control.

### Session theft and fixation
Tokens are 256-bit random values; only a peppered digest is stored, so a
database disclosure yields nothing usable. Cookies are `HttpOnly`, `Secure` in
production, and `SameSite=Lax`. Login always issues a fresh token; password
changes rotate the current session and revoke the rest. Sessions have both an
absolute expiry and an idle timeout, and can be revoked server-side —
suspension does so immediately.

### CSRF
Double-submit: the CSRF token's digest is stored on the session row and the
plaintext is placed in a readable cookie the frontend echoes in a header. A
cross-site attacker can cause the session cookie to be sent but cannot read the
CSRF cookie to construct the matching header. Comparison is constant-time.
`SameSite=Lax` is a second, independent layer.

### Cross-site scripting
React escapes by default and no code path uses `dangerouslySetInnerHTML`. The
response CSP is `default-src 'none'` for the API and same-origin for the app,
with `frame-ancestors 'none'` and `object-src 'none'`. Uploaded filenames are
reduced to a bare basename, bounded, and stripped of NUL bytes before storage;
extracted document text and feedback comments are rendered as text.

### SQL injection
Every query goes through SQLAlchemy with bound parameters. The admin user search
binds its pattern rather than interpolating it, and an integration test submits
`'; DROP TABLE users; --` and asserts the table survives and ordinary search
still works.

### IDOR and privilege escalation
Ownership is a **predicate in the query**, not a comparison after a lookup, so a
probe cannot distinguish "not yours" from "does not exist" — both return 404.
Every admin route depends on a server-side role check; the frontend guard is a
convenience only. Integration and end-to-end tests assert both boundaries, and
that a suspended administrator loses access immediately.

### Malicious documents
Extension **and** content signature are validated; the browser's MIME type is
never trusted. PDFs: encrypted files are refused with a clear message, page
count and extracted characters are bounded, and no annotation, embedded file, or
JavaScript action is executed. DOCX: every archive member is inspected **before**
extraction for path traversal, absolute paths, drive letters, symlinks, member
count, uncompressed total, and per-member compression ratio. Macros and embedded
objects are never executed and no external relationship target is fetched.
`.txt` uploads are rejected when they contain binary content.

Extraction happens entirely in memory, so no temporary file is left behind on
success or failure and none can be raced.

### Archive and decompression bombs
Member count, uncompressed total (80 MiB), and per-member compression ratio
(120:1) are bounded, checked from the archive's central directory before any
member is read. Tested with a fixture that expands 60 MiB from a few kilobytes.

### Denial of service through expensive inference
Size limits are enforced before inference. Pathologically repetitive input and
single tokens over 1,000 characters are rejected. Below the minimum word count
nothing is scored. Celery has soft and hard time limits, concurrency and
prefetch pinned to one, and `worker_max_tasks_per_child` to bound memory growth.
Rate limits cap submissions per client.

### Queue exhaustion and unsafe deserialization
Celery accepts JSON only; pickle would turn a queue write into remote code
execution. Tasks are idempotent and reject invalid state transitions, so a
redelivered message cannot double-process.

### Supply chain
`pip-audit` and `npm audit` run in CI on the pinned lockfiles and on a weekly
schedule, so an advisory published against an unchanged dependency is still
noticed. Model weights load from safetensors only. Pinning
`ORIGINLENS_MODEL_REVISION` to a commit SHA is documented as a production
requirement, since a tag can be moved after review. Dependabot groups patch and
minor updates and leaves majors individually reviewable; Torch and Transformers
majors are explicitly excluded from automation because they change model-loading
semantics — a change that broke this codebase twice and was caught only by the
real-provider test suite.

### Content leakage
This is the threat the design is organised around.

* Text is never passed to the logger. A redaction filter is installed as defence
  in depth, and content-bearing keys redact through end of line because their
  values are unbounded.
* Exception tracebacks are never logged or returned; only the exception type.
* FastAPI's default validation handler echoes the offending input, which here
  would return a slice of the user's document. It is replaced with one that
  reports field names only.
* Detector errors are bounded to 300 characters and carry a stable code, so a
  library exception cannot smuggle content into a response.
* Only an analysis id crosses the Celery queue.
* The admin console exposes counts and codes; no route returns submitted text.
* Playwright traces and screenshots can contain submitted text, so they are
  captured only on failure, retained briefly, and flagged for review before
  sharing.
* An integration test submits a sentinel string and asserts it appears in
  neither the captured logs nor the audit records.

### SSRF
No code path fetches a URL derived from submitted content or document metadata.
Document parsing does not resolve external relationships or remote resources.

### Unicode and homoglyph evasion
Invisible characters, mixed scripts, and homoglyphs are detected and reported as
integrity warnings; homoglyphs also reduce reliability. Characters are **not**
silently substituted — analysing a rewrite would mean reporting on a document
the user did not submit. *Residual:* a sufficiently careful transformation will
evade both the detector and the warnings.

### Privacy-preserving abuse control
Rate limiting needs to tell clients apart but does not need to know who they
are. Keys are an HMAC-SHA256 digest of the client identifier under a
server-side pepper, truncated to 128 bits; rotating the pepper invalidates every
stored identifier. An integration test asserts no plaintext identifier reaches
Redis.

### Secrets baked into container images
The Docker build contexts are `./backend` and `./frontend`, so the
repository-root `.dockerignore` does **not** apply to them. Without per-context
files a developer's local `.env` is copied into a distributable image layer,
where deleting it later does not remove it from the layer history. Both
contexts have their own `.dockerignore`, and CI asserts that no built image
contains a `.env` or a virtualenv.

### Secret leakage and unsafe configuration
Production start-up **fails closed** on placeholder secrets, short secrets,
debug mode, insecure cookies, `localhost` in the host allow-list, metrics
without a token, a loosened rate-limit multiplier, and the fake detector. The
registry independently refuses to build a fake provider in production. CI
asserts each refusal, and a secret-scan job refuses a committed `.env`, model
weights, databases, or build output.

## Residual risks

* **Compromise of the encryption key** discloses every retained submission.
  Envelopes are versioned so the algorithm and key can be rotated, but
  re-encrypting existing rows is a migration this project does not yet provide.
* **A malicious model checkpoint** runs inside the worker. Safetensors prevents
  code execution at load, but a deliberately mistrained model still produces
  misleading scores. Pin a revision and evaluate before deployment.
* **Timing side channels** in authentication are reduced but not eliminated.
* **A compromised administrator account** can suspend users and read aggregate
  statistics and the audit log. It cannot read submitted text.
* **Traffic between tiers** is assumed to be on a trusted network; the reference
  Compose file does not encrypt intra-stack traffic.
