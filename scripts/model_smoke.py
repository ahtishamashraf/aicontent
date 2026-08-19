#!/usr/bin/env python3
"""Real-model smoke test.

This deliberately does **not** assert a particular classification for a sample
sentence. A detector that returns "AI" for one crafted string proves nothing,
and encoding such an expectation would turn a green test into a false comfort.

What it does assert:

* the configured model loads with the configured revision;
* its label mapping is interpretable, so the AI class is known rather than guessed;
* at least one real inference runs;
* every window score is finite and inside [0, 1];
* the aggregate and calibrated public score are well-formed;
* the result schema and provenance fields are populated.

The observed score is printed for the operator to judge; it is not asserted.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings
from detection.aggregation import aggregate_windows
from detection.calibration import band_for, calibrate
from detection.engines.base import DetectorError
from detection.registry import build_provider

SAMPLE = (
    "The committee reviewed the revised proposal during the March session, and "
    "several members raised concerns about the delivery timeline. In particular, "
    "the assumption that procurement would complete before the summer recess "
    "struck two of them as optimistic. The chair agreed to circulate a revised "
    "schedule before the next meeting, noting that the archive migration had "
    "already slipped twice for related reasons. A second matter concerned "
    "staffing levels across the department, where two vacancies have gone "
    "unfilled since January and the workload has fallen on a smaller team than "
    "the original plan assumed."
)


def _fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 1


def main() -> int:
    settings = get_settings()

    if settings.detector_backend == "fake":
        return _fail(
            "ORIGINLENS_DETECTOR_BACKEND is 'fake'. The smoke test exists to "
            "exercise the real model; set it to 'modernbert' and retry."
        )

    print(f"Backend        : {settings.detector_backend}")
    print(f"Model          : {settings.model_id}")
    print(f"Revision       : {settings.model_revision or '(default branch)'}")
    print(f"Device request : {settings.model_device}")
    print()

    provider = build_provider(settings)

    print("Loading model...")
    try:
        provider.load()
    except DetectorError as exc:
        return _fail(f"[{exc.code}] {exc.detail}")

    metadata = provider.metadata()
    print(f"  device                : {metadata['device']}")
    print(f"  torch                 : {metadata.get('torch_version')}")
    print(f"  transformers          : {metadata.get('transformers_version')}")
    print(f"  resolved commit       : {metadata.get('resolved_commit') or '(unknown)'}")
    print(f"  labels                : {metadata.get('label_names')}")
    print(f"  AI label index        : {metadata.get('ai_label_index')}")
    print(f"  calibration version   : {metadata['calibration_version']}")
    print(f"  detector version      : {metadata['detector_version']}")
    print()

    if metadata.get("ai_label_index") is None:
        return _fail("The AI label index was not resolved")
    for field in ("model_id", "device", "torch_version", "transformers_version"):
        if not metadata.get(field):
            return _fail(f"Provenance field '{field}' is missing from metadata")

    print("Running inference...")
    try:
        window_scores = provider.score_text(SAMPLE)
    except DetectorError as exc:
        return _fail(f"[{exc.code}] {exc.detail}")

    if not window_scores.scores:
        return _fail("Inference produced no window scores")

    for index, score in enumerate(window_scores.scores):
        if score != score:  # NaN
            return _fail(f"Window {index} produced NaN")
        if score in (float("inf"), float("-inf")):
            return _fail(f"Window {index} produced a non-finite score")
        if not 0.0 <= score <= 1.0:
            return _fail(f"Window {index} produced {score}, outside [0, 1]")

    aggregate = aggregate_windows(window_scores.scores, window_scores.token_weights)
    public = calibrate(aggregate.raw_score)
    if not 0 <= public <= 100:
        return _fail(f"Calibrated score {public} is outside 0-100")

    print(f"  windows scored        : {aggregate.window_count}")
    print(f"  window scores         : {[round(s, 4) for s in aggregate.window_scores]}")
    print(f"  raw aggregate         : {aggregate.raw_score:.6f}")
    print(f"  window stability      : {aggregate.stability:.6f}")
    print()
    print(f"  observed public score : {public}  ({band_for(public).value})")
    print(
        "  NOTE: the score above is reported, not asserted. A single sample "
        "cannot validate a classifier."
    )
    print()
    print("PASS: model loaded, label mapping valid, inference finite and well-formed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
