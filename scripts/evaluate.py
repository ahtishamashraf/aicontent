#!/usr/bin/env python3
"""Evaluate the configured detector against a labelled dataset.

Usage::

    python scripts/evaluate.py                          # checked-in fixture set
    python scripts/evaluate.py --dataset my/raid.jsonl  # your own corpus

Dataset format is JSON Lines with ``id``, ``label`` ("human" or "ai"), ``text``,
and optional ``domain`` / ``source`` / ``attack`` metadata used for slicing.

Statistical honesty
-------------------
Small samples cannot support most of these metrics. Below ``MIN_SAMPLES_FOR_*``
the corresponding figure is withheld and the reason printed, rather than
reported with a spurious number of decimal places. A confusion matrix over ten
documents is a description of ten documents, not a measurement of a classifier.

Nothing here is a benchmark claim. Report the dataset, its size, and its
provenance alongside any figure produced.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings
from detection.calibration import Label
from detection.engines.base import DetectorError
from detection.pipeline import InputRejected, analyse
from detection.registry import build_provider

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[1] / "backend/tests/fixtures/evaluation/dataset.jsonl"
)

#: Thresholds below which a metric is withheld rather than reported.
MIN_SAMPLES_FOR_RATES = 30
MIN_SAMPLES_FOR_AUROC = 50
MIN_SAMPLES_FOR_CALIBRATION = 100
MIN_SAMPLES_PER_SLICE = 20


@dataclass
class Prediction:
    id: str
    truth: str
    score: int | None
    label: str
    reliability: str
    words: int
    domain: str | None = None
    source: str | None = None
    attack: str | None = None
    skipped_reason: str | None = None


@dataclass
class Confusion:
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    @property
    def total(self) -> int:
        return self.true_positive + self.false_positive + self.true_negative + self.false_negative

    def accuracy(self) -> float | None:
        return (self.true_positive + self.true_negative) / self.total if self.total else None

    def precision(self) -> float | None:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else None

    def recall(self) -> float | None:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else None

    def f1(self) -> float | None:
        precision, recall = self.precision(), self.recall()
        if precision is None or recall is None or precision + recall == 0:
            return None
        return 2 * precision * recall / (precision + recall)

    def false_positive_rate(self) -> float | None:
        denominator = self.false_positive + self.true_negative
        return self.false_positive / denominator if denominator else None

    def false_negative_rate(self) -> float | None:
        denominator = self.false_negative + self.true_positive
        return self.false_negative / denominator if denominator else None


def load_dataset(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Dataset not found: {path}")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number}: invalid JSON ({exc.msg})") from exc
        if record.get("label") not in {"human", "ai"}:
            raise SystemExit(f"{path}:{number}: label must be 'human' or 'ai'")
        if not record.get("text"):
            raise SystemExit(f"{path}:{number}: 'text' is required")
        records.append(record)
    if not records:
        raise SystemExit(f"{path} contains no samples")
    return records


def auroc(scores: list[tuple[int, int]]) -> float | None:
    """Rank-based AUROC. ``scores`` is (score, truth) with truth 1 for AI."""
    positives = [s for s, t in scores if t == 1]
    negatives = [s for s, t in scores if t == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            wins += 1.0 if p > n else 0.5 if p == n else 0.0
    return wins / (len(positives) * len(negatives))


def expected_calibration_error(scores: list[tuple[int, int]], bins: int = 10) -> float | None:
    """ECE over equal-width bins, treating score/100 as a claimed probability."""
    if not scores:
        return None
    buckets: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for score, truth in scores:
        buckets[min(int(score / 100 * bins), bins - 1)].append((score, truth))
    total = len(scores)
    error = 0.0
    for entries in buckets.values():
        confidence = sum(s for s, _ in entries) / len(entries) / 100
        accuracy = sum(t for _, t in entries) / len(entries)
        error += len(entries) / total * abs(confidence - accuracy)
    return error


def _fmt(value: float | None, *, percent: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%" if percent else f"{value:.4f}"


def build_confusion(predictions: list[Prediction]) -> Confusion:
    """AI-patterned counts as a positive prediction; uncertain is not."""
    confusion = Confusion()
    for prediction in predictions:
        if prediction.score is None:
            continue
        predicted_ai = prediction.label == Label.AI_PATTERNED.value
        actually_ai = prediction.truth == "ai"
        if predicted_ai and actually_ai:
            confusion.true_positive += 1
        elif predicted_ai and not actually_ai:
            confusion.false_positive += 1
        elif not predicted_ai and actually_ai:
            confusion.false_negative += 1
        else:
            confusion.true_negative += 1
    return confusion


def report(predictions: list[Prediction], dataset_path: Path, settings: Any) -> None:
    scored = [p for p in predictions if p.score is not None]
    skipped = [p for p in predictions if p.score is None]
    n = len(scored)

    print("=" * 74)
    print("OriginLens evaluation")
    print("=" * 74)
    print(f"Dataset            : {dataset_path}")
    print(f"Backend            : {settings.detector_backend}")
    print(f"Model              : {settings.model_id}")
    print(f"Revision           : {settings.model_revision or '(default branch)'}")
    print()
    print(f"Samples supplied   : {len(predictions)}")
    print(f"Samples scored     : {n}")
    print(f"Samples skipped    : {len(skipped)}")
    if skipped:
        reasons: dict[str, int] = defaultdict(int)
        for prediction in skipped:
            reasons[prediction.skipped_reason or "unknown"] += 1
        for reason, count in sorted(reasons.items()):
            print(f"    {reason}: {count}")

    truth_counts = defaultdict(int)
    for prediction in scored:
        truth_counts[prediction.truth] += 1
    print(f"Class balance      : human={truth_counts['human']} ai={truth_counts['ai']}")
    print()

    if n == 0:
        print("No samples were scored; there is nothing to report.")
        return

    confusion = build_confusion(scored)
    print("Confusion matrix (positive = 'Likely AI-patterned')")
    print(f"    true positive  : {confusion.true_positive}")
    print(f"    false positive : {confusion.false_positive}")
    print(f"    true negative  : {confusion.true_negative}")
    print(f"    false negative : {confusion.false_negative}")
    print()

    if n < MIN_SAMPLES_FOR_RATES:
        print(
            f"Accuracy, precision, recall, F1, FPR and FNR are WITHHELD: {n} scored "
            f"samples is below the {MIN_SAMPLES_FOR_RATES}-sample minimum.\n"
            "    A rate over this few documents describes the documents, not the "
            "classifier."
        )
    else:
        print(f"Accuracy           : {_fmt(confusion.accuracy(), percent=True)}")
        print(f"Precision          : {_fmt(confusion.precision(), percent=True)}")
        print(f"Recall             : {_fmt(confusion.recall(), percent=True)}")
        print(f"F1                 : {_fmt(confusion.f1())}")
        print(f"False positive rate: {_fmt(confusion.false_positive_rate(), percent=True)}")
        print(f"False negative rate: {_fmt(confusion.false_negative_rate(), percent=True)}")
    print()

    pairs = [(p.score, 1 if p.truth == "ai" else 0) for p in scored if p.score is not None]
    if n < MIN_SAMPLES_FOR_AUROC:
        print(f"AUROC              : WITHHELD ({n} < {MIN_SAMPLES_FOR_AUROC} samples)")
    else:
        print(f"AUROC              : {_fmt(auroc(pairs))}")

    if n < MIN_SAMPLES_FOR_CALIBRATION:
        print(f"Calibration error  : WITHHELD ({n} < {MIN_SAMPLES_FOR_CALIBRATION} samples)")
    else:
        print(f"Expected calib. err: {_fmt(expected_calibration_error(pairs))}")
        print(
            "    NOTE: the active calibration is the identity mapping, so this "
            "figure measures how far that assumption is from reality."
        )
    print()

    for dimension in ("domain", "source", "attack"):
        slices: dict[str, list[Prediction]] = defaultdict(list)
        for prediction in scored:
            value = getattr(prediction, dimension)
            if value:
                slices[value].append(prediction)
        if not slices:
            continue
        print(f"By {dimension}:")
        for name, entries in sorted(slices.items()):
            if len(entries) < MIN_SAMPLES_PER_SLICE:
                print(
                    f"    {name:<18} n={len(entries):<4} metrics withheld "
                    f"(< {MIN_SAMPLES_PER_SLICE} samples)"
                )
            else:
                sliced = build_confusion(entries)
                print(
                    f"    {name:<18} n={len(entries):<4} "
                    f"accuracy={_fmt(sliced.accuracy(), percent=True)} "
                    f"FPR={_fmt(sliced.false_positive_rate(), percent=True)}"
                )
        print()

    lengths = defaultdict(list)
    for prediction in scored:
        bucket = (
            "<150 words"
            if prediction.words < 150
            else "150-499 words"
            if prediction.words < 500
            else "500+ words"
        )
        lengths[bucket].append(prediction)
    print("By length:")
    for name, entries in sorted(lengths.items()):
        if len(entries) < MIN_SAMPLES_PER_SLICE:
            print(
                f"    {name:<18} n={len(entries):<4} metrics withheld "
                f"(< {MIN_SAMPLES_PER_SLICE} samples)"
            )
        else:
            sliced = build_confusion(entries)
            print(
                f"    {name:<18} n={len(entries):<4} "
                f"accuracy={_fmt(sliced.accuracy(), percent=True)}"
            )
    print()
    print("-" * 74)
    print(
        "These figures describe this dataset only. Report the dataset, its size, "
        "and its provenance with any number taken from here."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", type=Path, default=None, help="Write raw predictions")
    args = parser.parse_args()

    settings = get_settings()
    records = load_dataset(args.dataset)

    provider = build_provider(settings)
    try:
        provider.load()
    except DetectorError as exc:
        print(f"Model failed to load: [{exc.code}] {exc.detail}", file=sys.stderr)
        return 1

    if settings.detector_backend == "fake":
        print(
            "WARNING: the fake detector is selected. The numbers below exercise "
            "the harness and mean nothing about detection quality.\n",
            file=sys.stderr,
        )

    predictions: list[Prediction] = []
    for record in records:
        try:
            result = analyse(record["text"], provider, settings, include_paragraph_text=False)
        except InputRejected as exc:
            predictions.append(
                Prediction(
                    id=record["id"],
                    truth=record["label"],
                    score=None,
                    label="rejected",
                    reliability="n/a",
                    words=len(record["text"].split()),
                    domain=record.get("domain"),
                    source=record.get("source"),
                    attack=record.get("attack"),
                    skipped_reason=exc.code,
                )
            )
            continue

        predictions.append(
            Prediction(
                id=record["id"],
                truth=record["label"],
                score=result.public_score,
                label=result.label,
                reliability=result.reliability,
                words=result.word_count,
                domain=record.get("domain"),
                source=record.get("source"),
                attack=record.get("attack"),
                skipped_reason=(None if result.public_score is not None else result.label),
            )
        )

    report(predictions, args.dataset, settings)

    if args.json:
        args.json.write_text(json.dumps([vars(p) for p in predictions], indent=2), encoding="utf-8")
        print(f"\nRaw predictions written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
