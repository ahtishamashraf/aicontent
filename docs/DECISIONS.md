# Design decisions

Decisions where a different choice was plausible, and why this one was made.

## The score is not called a probability

**Decision.** The public score is the model's raw output × 100 — the identity
mapping — and its version string is literally `identity-1.0.0`.

**Why.** A calibrated score of 70 would mean such documents are
machine-generated about 70% of the time. Establishing that needs a large,
representative, labelled dataset and a published reliability diagram. This
project has neither. Presenting an uncalibrated logit as a probability is the
single most common dishonesty in this product category, and the version string
is written so that nobody — including a future maintainer — can mistake what it
is. The evaluation harness withholds calibration error below 100 samples for the
same reason.

## Diagnostics are never blended into the score

**Decision.** Sentence-length variation, lexical variety, repetition rates and
the rest are reported as context and are *not* inputs to the score. The
diagnostics payload deliberately carries no `score` or `label` field.

**Why.** Combining them would need weights, and no validated weighting exists.
Inventing coefficients and presenting the total as a measurement is
pseudo-science wearing a lab coat, and it would be indistinguishable from the
real classifier in the output. Keeping them structurally separate makes the
boundary enforceable rather than aspirational.

## Reliability is an enum with reasons, not a percentage

**Decision.** Results carry `insufficient` / `low` / `moderate` / `normal` plus
a list of plain-language reasons.

**Why.** "87% confident" implies a calibrated uncertainty model. "Only 100 words
were analysed" is both true and actionable. The reason list also makes the
system's own doubts legible to a reader deciding how much weight to give it.

**Trade-off.** Harder to sort or threshold programmatically. That is acceptable:
the value should not be used that way.

## Strong window disagreement forces "uncertain"

**Decision.** When the standard deviation across window scores reaches 0.28, the
label becomes `Uncertain or mixed signals` regardless of the average.

**Why.** A document whose halves score 0.05 and 0.95 averages to something
confident-looking. That average describes neither half. Mixed evidence is itself
the finding, and reporting it as a verdict would be the most misleading thing
the system could do.

## Very short paragraphs get no score at all

**Decision.** Below 15 words a paragraph is marked `too_short` with a null
score, even though neighbouring context would produce a number.

**Why.** This was found by a test. A one-word paragraph was being scored 77 from
borrowed context — a confident number attached to a heading, measuring its
neighbours rather than itself. Grouping gives *context* for a moderately short
paragraph; below the floor there is nothing to contextualise.

## The AI class is resolved from labels, never from index order

**Decision.** The provider reads `id2label`, cross-checks `label2id`, and
**refuses to load** a checkpoint whose mapping is absent, generic, ambiguous, or
contradictory.

**Why.** Roughly half of published checkpoints put the AI class at index 0 and
half at index 1. Assuming one produces confident, plausible, exactly-inverted
predictions on the other half — the worst failure mode available, because
nothing looks broken.

## No fallback from the real detector to the fake one

**Decision.** A load or inference failure surfaces as `analysis_unavailable`.
The registry never substitutes the fake provider, and production refuses to
build one at all.

**Why.** A fabricated score is worse than an honest error. An error is visible
and gets fixed; a plausible number derived from a hash gets acted on.

## The fake detector is named "fake" everywhere

**Decision.** In settings, in health output, and in the provenance recorded on
every result — including a `warning` field and `is_real_model: false`.

**Why.** Anything blander ("stub", "default", "local") eventually gets deployed
by someone who did not read the docs. The settings layer refuses it in
production, the registry refuses it independently, and CI asserts both.

## Sessions are opaque and server-side, not JWTs

**Decision.** Random tokens with only a peppered digest stored server-side.

**Why.** Revocation. Suspending a user must end their session *now*, and a
stateless token cannot be recalled without building the revocation list that
made it stateful anyway. The database lookup this costs is negligible next to an
inference.

## `GET /auth/session` returns 200 with a null user

**Decision.** It does not return 401 for an anonymous visitor.

**Why.** "Not signed in" is a valid answer to "who am I". Returning 401 made
every guest page load emit a browser console error, which then hides real ones —
and §19's "no uncaught console errors" is only a meaningful check if the
baseline is actually clean.

## Ownership is a query predicate, not a post-hoc comparison

**Decision.** Analyses are loaded with an ownership condition in the `WHERE`
clause, and a miss returns 404 rather than 403.

**Why.** Fetching then comparing leaves a window for a mistaken early return,
and 403 confirms the row exists — precisely what an IDOR probe wants. Both
outcomes are made indistinguishable.

## Rate limiting stores digests, never IP addresses

**Decision.** Keys are an HMAC-SHA256 digest of the client identifier under a
server-side pepper.

**Why.** Abuse control needs to tell clients apart; it does not need to know who
they are. Rotating the pepper invalidates every stored identifier, which is a
meaningful privacy control rather than a promise.

## Authentication rate limiting fails closed

**Decision.** Login refuses requests when Redis is unreachable. Ordinary traffic
fails open.

**Why.** Failing open on authentication turns a cache outage into an unlimited
credential-stuffing window. Failing closed on analysis would turn the same
outage into a full outage. The two paths have different costs, so they get
different behaviour, and the choice is a parameter at the call site rather than
a global.

## Only an analysis id crosses the queue

**Decision.** The worker reads submitted text from the database rather than
receiving it in the task payload.

**Why.** Redis would otherwise hold document content in queue entries, task
results, and any debug tooling pointed at it. A UUID is enough.

## Document extraction happens in memory

**Decision.** No temporary file is written.

**Why.** A temp file is a race and a cleanup obligation that fails exactly when
things go wrong. Uploads are bounded at 5 MiB, so holding one in memory is
cheaper than managing a file whose deletion has to survive every error path.

## Archive members are inspected before extraction

**Decision.** A DOCX's central directory is checked for traversal, absolute
paths, symlinks, member count, uncompressed total, and compression ratio before
any member is read.

**Why.** Checking during extraction means the bomb has already partly
detonated. The central directory contains everything needed to refuse first.

## Homoglyphs are reported, not rewritten

**Decision.** Confusable characters are flagged and reduce reliability, but are
not substituted.

**Why.** Rewriting and then analysing the rewrite means reporting on a document
the user did not submit. The user is told what was found and can decide.

## The frontend reads limits from the API

**Decision.** Limits, band thresholds, and disclaimers come from
`GET /api/v1/config`.

**Why.** Duplicated constants drift, and the failure is silent: the UI promises
one limit while the server enforces another. One source of truth costs one
request.

## Upgrading dependency majors during the build

**Decision.** Next 15→16, Vitest 2→4, Starlette 0→1, pytest 8→9, Transformers
4→5 were adopted mid-build.

**Why.** Audits reported 12 npm advisories (two critical) and 61 Python
advisories, including in the PDF parser that exists to read hostile uploads.
Since little code had been written against the old APIs, upgrading was cheaper
than deferring, and both audits are now clean. This is not a licence to track
latest: Dependabot leaves majors individually reviewable, and Torch and
Transformers majors are excluded from automation because they change
model-loading semantics — as this upgrade demonstrated by breaking the provider
twice.
