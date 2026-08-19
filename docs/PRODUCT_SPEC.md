# Product specification

## What OriginLens is

A self-hosted analyser that reports whether English prose carries stylistic
patterns associated with machine generation, together with an honest statement
of how much weight that finding can bear.

## What it is not

An authorship detector. It has no access to the writing process and no
provenance signal. It measures surface statistics, and surface statistics do not
establish who wrote something.

## Users

| User | Needs |
| --- | --- |
| Guest | Analyse a passage without an account; a result they can read and discard |
| Registered user | A history, optional retention of submitted text, and the ability to delete both |
| Administrator | Account management, service health, and an audit trail — with no access to submitted content |

## Core flows

### Guest analysis
Paste text or upload a document → result page with band, reliability, reasons,
paragraph breakdown, statistics, and disclaimers → optionally export JSON,
print, or leave feedback. The text is discarded; the result link expires.

### Registered analysis
As above, plus persistent history, an opt-in to retain the submitted text
(encrypted), and deletion of either individually or wholesale.

### Administration
Suspend and reactivate accounts, view aggregate statistics and feedback, edit
typed settings, read the audit log, and inspect model health. No route reaches
submitted content.

## Result semantics

| Element | Rule |
| --- | --- |
| Score | 0–100, or **null** when nothing was scored. Never `0` as a stand-in. |
| Band | `Likely human-patterned` (0–34), `Uncertain or mixed signals` (35–64), `Likely AI-patterned` (65–100) |
| Reliability | An enum with reasons, never a confidence percentage |
| Paragraphs | Scored only with sufficient evidence; otherwise `not scored` |
| Disclaimers | Travel with the result on screen, in print, and in the export |

Special outcomes:

* **`Insufficient text`** below 80 words — returned before any inference runs.
* **`Unsupported language`** when English confidence is below threshold.
* **`analysis_unavailable`** when the detector cannot run. No score is invented.

## Non-negotiable product rules

1. Never present the score as proof of authorship.
2. Never publish an accuracy figure that has not been measured on a dataset that
   supports it.
3. Never show a number where the evidence does not support one.
4. Never substitute a fabricated result for an unavailable model.
5. Never hide the limitations — they are linked from the main navigation.
6. Never let an administrator read submitted text.
7. Never store a plaintext IP address, session token, or password.

## Interface requirements

* Responsive from 320 px with no horizontal overflow.
* Every interactive component implements default, hover, focus-visible, active,
  disabled, loading, success, validation-error, and server-error states.
* WCAG 2.2 AA contrast; colour never the sole carrier of meaning.
* The primary flow completable with the keyboard alone.
* Dialogs manage focus; status changes are announced politely.
* `prefers-reduced-motion` honoured.
* Print output keeps the result and its disclaimer and drops the interface.

## Limits

Configured server-side and reported by `GET /api/v1/config`, which the frontend
reads rather than duplicating: 80 minimum words, 150 for normal length
reliability, 10,000 words / 50,000 characters maximum, 5 MiB uploads,
`.txt` / `.pdf` / `.docx` only.

## Out of scope

Non-English analysis; OCR of scanned PDFs; real-time collaboration; a public
API for third-party integration; a mobile application; any feature whose output
would be a stronger claim than the evidence supports.
