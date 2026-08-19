# Evaluation fixture set

A small, checked-in set used to make `make evaluate` runnable out of the box.

## Provenance and licensing

Every sample here is either:

* **synthetic** — written for this repository, or
* **public domain** — drawn from works published before 1900 whose copyright has
  long expired.

No real submitted user writing appears here, and none ever should. The
`human/` samples are *not* evidence that a human wrote them in any adversarial
sense; they are ordinary prose used to check that the pipeline runs and reports
plausible, well-formed output.

## What this set is not

It is far too small to measure accuracy. Ten samples cannot establish a false
positive rate, and a metric computed over them would be noise presented as a
number. `scripts/evaluate.py` therefore refuses to report AUROC or calibration
error below a documented sample threshold, and prints the reason.

For a real measurement, supply a larger labelled corpus with
`--dataset path/to/dataset.jsonl`. See `docs/DETECTION_METHODOLOGY.md`.

## Format

`dataset.jsonl`, one JSON object per line:

```json
{"id": "human-001", "label": "human", "text": "...", "domain": "essay", "source": "synthetic"}
```

`label` is `human` or `ai`. `domain`, `source`, and `attack` are optional
metadata used to break metrics down by slice.
