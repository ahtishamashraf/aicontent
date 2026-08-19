# Detection methodology

How a submission becomes a score, and what each step is and is not entitled to
claim.

## 1. Two copies of the text

The submitter's bytes are preserved exactly as `display_text`. A separate
`analysis_text` is derived for tokenization and statistics:

* line endings canonicalised to `\n`;
* NFC normalisation, which does not change the author's words;
* invisible formatting characters and control characters removed;
* runs of horizontal whitespace collapsed to a single space;
* consecutive blank lines capped at one.

Words, punctuation, casing, and paragraph boundaries survive intact, so
diagnostics measure the author's writing rather than an artefact of cleaning.

Integrity findings are reported to the reader, not silently corrected:

| Code | Meaning |
| --- | --- |
| `invisible_characters` | Zero-width or bidirectional marks were present |
| `mixed_scripts` | Latin text mixed with another writing system |
| `homoglyph_risk` | Characters resembling Latin letters from another script |
| `excessive_whitespace` | Unusually long whitespace or blank-line runs |
| `control_characters` | Control bytes were present |

Homoglyphs are flagged but **not** substituted. Rewriting the author's
characters and then analysing the rewrite would mean reporting on a document
they did not submit.

## 2. Language routing

Detection uses `langdetect`, a local port of Nakagawa and Ienaga's profiles. It
makes no network calls, so the text never leaves the deployment for this step,
and the detector is seeded so identical input yields an identical verdict.

The baseline is **English only**. Below the configured confidence threshold
(default 0.60) the result is `Unsupported language` with no score. A failed
detection is reported as `unknown` and unsupported, never assumed to be English.

## 3. Length gating

Checked before any inference, so a hopeless submission costs nothing:

| Words | Behaviour |
| --- | --- |
| < 80 | `Insufficient text`. No score. |
| 80–149 | Analysed, marked **low** reliability with the reason stated. |
| ≥ 150 | Analysed at normal reliability, subject to the other factors below. |

Oversized, empty, binary, pathologically repetitive, and single-huge-token
inputs are rejected with distinct codes.

## 4. Windowing

The analysis copy is tokenized with the **model's own tokenizer** and split
into overlapping windows of at most `model_max_tokens` (default 384) advancing
by `model_stride` (default 320), giving a 64-token overlap.

Windows are never built by slicing characters. A character slice can cut a word
or a multi-byte grapheme in half, silently changing what the model sees. The
number of special tokens the tokenizer wraps content in is measured at load
time and subtracted from the budget, so a window can never overflow the model's
context.

A trailing window shorter than a quarter of the stride is dropped rather than
scored on a sliver of mostly-overlapping text.

## 5. Aggregation and disagreement

Each window yields a probability for the AI class. These are combined
**weighted by token count**, so a short trailing window does not count as much
as a full one.

The population standard deviation across window scores is recorded as
`window_stability`:

| Disagreement | Effect |
| --- | --- |
| < 0.18 | No effect |
| 0.18–0.28 | Reliability reduced to **moderate** |
| ≥ 0.28 | Reliability reduced to **low**, and the label forced to `Uncertain or mixed signals` |

The override matters: a document whose halves score 0.05 and 0.95 averages to
something confident-looking, and presenting that as a verdict would be wrong.
Strong internal disagreement is itself the finding.

## 6. Score semantics

The model's raw output is stored in `raw_model_score`. The public score is
`round(raw × 100)` — **the identity mapping** — and its version string is
`identity-1.0.0` so nobody can mistake it for something fitted.

A calibrated score would mean documents scoring 70 are machine-generated about
70% of the time. Establishing that requires a large, representative, labelled
dataset and a published reliability diagram. This project ships neither, so the
API never calls the score a probability, and the evaluation harness withholds
calibration error below 100 samples.

### Display bands

| Range | Label |
| --- | --- |
| 0–34 | Likely human-patterned |
| 35–64 | Uncertain or mixed signals |
| 65–100 | Likely AI-patterned |

Thresholds live in one versioned module and are served to the frontend, so the
UI cannot drift from the backend that enforces them.

### Reliability

A reliability **enum** with a **reason list** is returned, not a confidence
percentage. A percentage would imply a calibrated uncertainty model that does
not exist. Reliability is reduced by short text, window disagreement, and
integrity warnings, and each reduction states its reason.

## 7. Paragraph attribution

| Paragraph length | Treatment |
| --- | --- |
| < 15 words | `too_short`, **no score** |
| 15–39 words | Scored with neighbouring context, flagged `grouped_with_context` |
| ≥ 40 words | Scored on its own |

The 15-word floor is absolute. Borrowing context for a one-line paragraph would
measure the neighbours, not the paragraph, and a confident-looking number
beside a heading is false precision.

Every paragraph colour in the UI derives from that paragraph's own score.

## 8. Diagnostics

Reported alongside the result as **context**:

sentence-length mean, standard deviation and coefficient of variation;
paragraph-length variation; moving-average type–token ratio; repeated 2-, 3-,
and 4-gram rates; repeated sentence openings; punctuation distribution;
function-word distribution; transition-phrase density from a versioned list;
consecutive-sentence structural similarity; and window consistency.

MATTR is used rather than a raw type–token ratio because raw TTR falls as
length grows, which would make it a proxy for word count rather than for
lexical variety.

**These are not inputs to the score.** There is no validated weighting that
would justify combining them, and inventing one would be pseudo-science dressed
as a measurement. The diagnostics payload deliberately carries no `score` or
`label` field so it cannot quietly become a second classifier. The UI says so
on the panel.

## 9. The model provider

The model ID and revision are configuration. The provider resolves which output
index means "AI" from the checkpoint's `id2label`, cross-checked against
`label2id`, and **refuses to load** when the mapping is absent, generic
(`LABEL_0`/`LABEL_1`), ambiguous, contradictory, or non-binary.

Assuming index order would invert every prediction on half of all checkpoints —
a failure that produces confident, plausible, exactly-wrong answers.

Only safetensors checkpoints are loaded; a pickle checkpoint executes code at
load time. Weights load once per process. There is no fallback from the real
provider to the fake one.

## What this method cannot do

It measures surface statistics of text. It has no access to the writing
process, no provenance signal, and no way to distinguish a careful human
imitating a formal register from a machine producing one. See
[`MODEL_CARD.md`](MODEL_CARD.md) for the failure modes this implies.
