# Model card

## Overview

| | |
| --- | --- |
| **System** | OriginLens AI-signal analyser |
| **Task** | Binary sequence classification over English prose |
| **Output** | A 0–100 signal score, a display band, and a reliability level with reasons |
| **Model** | Configurable via `ORIGINLENS_MODEL_ID`; no checkpoint is bundled |
| **Calibration** | Identity mapping (`identity-1.0.0`) — see below |
| **Detector version** | `1.0.0` |

The deployment operator chooses the checkpoint. This project supplies the
pipeline, the safety controls, and the honesty constraints around it; it does
not train or endorse a particular model.

## Intended use

* Giving a reader a **starting signal** about whether writing carries patterns
  associated with machine generation.
* Prompting a **conversation**, a request for drafts, or a closer look — the
  kind of follow-up a human would do anyway.
* Aggregate, non-identifying analysis over a corpus.

## Out of scope, and prohibited

**Do not use an OriginLens score as the sole basis for a decision about a
person.** Specifically, not for:

* academic misconduct findings or grading;
* hiring, promotion, or termination;
* contract termination or payment disputes;
* immigration, benefits, or legal proceedings;
* any published claim that a named individual used AI.

The system cannot determine authorship. It reports a statistical resemblance,
and resemblance is not evidence.

## Known failure modes

| Population or condition | Effect | Why |
| --- | --- | --- |
| **Non-native English writers** | **False positives** | Second-language prose is often more regular in sentence structure and narrower in vocabulary — the same surface features associated with generated text. This is the most serious known failure, and it falls hardest on people least able to contest the result. |
| Formulaic or technical genres | False positives | Legal boilerplate, lab reports, and standards documents are conventionally repetitive. |
| Editing tools | Either direction | Grammar and style checkers move human text toward the machine-like end. |
| Heavily edited generated text | False negatives | Substantial human rewriting removes the signal. |
| Machine translation | False positives | Translation flattens style regardless of who wrote the original. |
| Paraphrasing tools | False negatives | These exist specifically to defeat detectors. |
| Homoglyph and invisible-character substitution | Either direction | Reported as an integrity warning when detected; absence of a warning is not proof of absence. |
| Short text | Unreliable | Below 80 words nothing is scored; 80–149 words is marked low reliability. |
| Non-English text | Not analysed | Reported as `Unsupported language`. |
| Domain shift | Unquantified | Performance on a genre unlike the training distribution is unknown. |

## Performance

**No accuracy figure is published, because none has been measured on a dataset
large or representative enough to support the claim.**

The repository ships an evaluation harness (`make evaluate`) and a ten-sample
fixture set of public-domain and synthetic text. Ten samples cannot establish a
false-positive rate, so the harness **withholds** accuracy, precision, recall,
F1, AUROC, and calibration error below documented thresholds and prints the
reason instead of reporting a number with spurious precision.

To measure performance, supply your own labelled corpus:

```bash
python scripts/evaluate.py --dataset path/to/your.jsonl
```

Report the dataset, its size, and its provenance alongside any figure produced.
A single headline accuracy number for AI text detection describes the test set,
not the next document.

## Calibration

The active calibration is the **identity mapping**: the public score is the
model's raw output multiplied by 100.

It is not a probability. A calibrated score of 70 would mean such documents are
machine-generated about 70% of the time, which requires a held-out labelled set
and a published reliability diagram. Neither exists here, so:

* the API never labels the score a probability;
* the calibration version string is literally `identity-1.0.0`;
* every result carries the calibration version so a stored result remains
  interpretable if calibration later changes.

## Reliability signalling

Rather than a fabricated confidence percentage, every result carries a
reliability enum (`insufficient`, `low`, `moderate`, `normal`) and a list of
plain-language reasons. Reliability is reduced by short text, disagreement
between sections of the document, and content-integrity warnings.

When sections of a document disagree strongly, the label is forced to
`Uncertain or mixed signals` regardless of the average — a mixed document
should not be presented as a confident verdict at either end.

## Ethical considerations

The costs of the two error types are not symmetric. A false negative means a
generated document goes unremarked. A **false positive can mean an accusation
against a person**, and the populations most exposed to it — non-native
speakers, writers in formulaic genres, people who use accessibility and
grammar tools — are frequently those with the least standing to object.

The product is built around that asymmetry: reliability is surfaced next to the
score rather than buried, genuinely mixed evidence is reported as uncertain
rather than resolved, short text yields no score at all, disclaimers travel with
the result into print and export, and the limitations page is linked from the
main navigation rather than hidden in a footer.

## Supply chain

* Weights load from safetensors only; a pickle checkpoint executes code on load.
* Pin `ORIGINLENS_MODEL_REVISION` to a commit SHA in production. A tag or branch
  can be moved by the publisher after review.
* The resolved commit, model ID, revision, device, and the Transformers and
  PyTorch versions are recorded on every result.
* Nothing is sent to an external model provider at inference time.

## Maintenance

Re-examine this card when the checkpoint, the calibration, the thresholds, or
the windowing parameters change. Every result records the detector and
calibration versions so stored results remain interpretable across such changes.
