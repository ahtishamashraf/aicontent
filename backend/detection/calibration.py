"""Versioned score calibration, display bands, and reliability rules.

Honesty note
------------
No validated calibration dataset ships with this project. The active
calibration is therefore the **identity mapping**: the public score is the raw
aggregated model output multiplied by 100 and rounded. It is *not* a
probability, and the API never labels it as one. Replacing this with a fitted
mapping requires a held-out labelled set and a recorded reliability diagram;
until then the identity mapping is the only defensible choice, and saying so is
part of the product.

The backend is the source of truth for every threshold here. The frontend
renders what it is given.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: Bump whenever a threshold, band, or the mapping function changes.
CALIBRATION_VERSION = "identity-1.0.0"

#: Bump when the scoring pipeline's behaviour changes.
DETECTOR_VERSION = "1.0.0"


class Label(StrEnum):
    HUMAN_PATTERNED = "Likely human-patterned"
    UNCERTAIN = "Uncertain or mixed signals"
    AI_PATTERNED = "Likely AI-patterned"
    INSUFFICIENT = "Insufficient text"
    UNSUPPORTED_LANGUAGE = "Unsupported language"


class Reliability(StrEnum):
    INSUFFICIENT = "insufficient"
    LOW = "low"
    MODERATE = "moderate"
    NORMAL = "normal"


@dataclass(frozen=True)
class Band:
    lower: int
    upper: int
    label: Label


#: Display bands, inclusive of both bounds. Documented in the product spec.
BANDS: tuple[Band, ...] = (
    Band(0, 34, Label.HUMAN_PATTERNED),
    Band(35, 64, Label.UNCERTAIN),
    Band(65, 100, Label.AI_PATTERNED),
)

#: Window disagreement at or above this standard deviation is "significant".
STABILITY_WARNING_STDEV = 0.18

#: Disagreement at or above this level forces the uncertain band.
STABILITY_FORCE_UNCERTAIN_STDEV = 0.28

#: A paragraph needs at least this many words to be scored on its own.
MIN_PARAGRAPH_WORDS_FOR_SCORE = 40

#: Absolute floor. A paragraph shorter than this is never given a score, even
#: when neighbouring context would produce one: attributing a two-decimal
#: verdict to a heading or a one-line reply is false precision, and borrowed
#: context would be measuring the neighbour rather than the paragraph.
ABSOLUTE_MIN_PARAGRAPH_WORDS = 15


def calibrate(raw_score: float) -> int:
    """Map a raw model score in [0, 1] to the public 0-100 signal score.

    Currently the identity mapping. See the module docstring.
    """
    clamped = min(max(raw_score, 0.0), 1.0)
    return round(clamped * 100)


def band_for(score: int) -> Label:
    """Return the display band label for a public score."""
    for band in BANDS:
        if band.lower <= score <= band.upper:
            return band.label
    raise ValueError(f"score {score} is outside 0-100")


def bands_as_dicts() -> list[dict[str, object]]:
    """Serialisable band table, so the UI never hard-codes thresholds."""
    return [{"lower": b.lower, "upper": b.upper, "label": b.label.value} for b in BANDS]


@dataclass
class ReliabilityAssessment:
    level: Reliability
    reasons: list[str]


def assess_reliability(
    *,
    word_count: int,
    window_stability: float | None,
    min_words: int,
    low_reliability_words: int,
    integrity_warning_codes: list[str],
    window_count: int,
) -> ReliabilityAssessment:
    """Derive a reliability enum and human-readable reasons.

    A reason list is returned instead of a fabricated confidence percentage:
    a percentage would imply a calibrated uncertainty model that does not exist.
    """
    reasons: list[str] = []

    if word_count < min_words:
        return ReliabilityAssessment(
            Reliability.INSUFFICIENT,
            [f"At least {min_words} words are required for any analysis."],
        )

    level = Reliability.NORMAL

    if word_count < low_reliability_words:
        level = Reliability.LOW
        reasons.append(
            f"Only {word_count} words were analysed; results below "
            f"{low_reliability_words} words are less reliable."
        )

    if window_stability is not None and window_count > 1:
        if window_stability >= STABILITY_FORCE_UNCERTAIN_STDEV:
            level = Reliability.LOW
            reasons.append(
                "Sections of the text scored very differently from one another, "
                "which is common in mixed or edited writing."
            )
        elif window_stability >= STABILITY_WARNING_STDEV:
            if level == Reliability.NORMAL:
                level = Reliability.MODERATE
            reasons.append("Sections of the text scored somewhat differently from one another.")

    if "homoglyph_risk" in integrity_warning_codes:
        level = Reliability.LOW if level != Reliability.INSUFFICIENT else level
        reasons.append(
            "Characters from another script resemble Latin letters, which can distort analysis."
        )
    if "invisible_characters" in integrity_warning_codes:
        if level == Reliability.NORMAL:
            level = Reliability.MODERATE
        reasons.append("Invisible characters were removed before analysis.")

    return ReliabilityAssessment(level, reasons)


def apply_stability_override(score: int, window_stability: float | None) -> Label:
    """Return the display label, forcing 'uncertain' on strong disagreement.

    Genuinely mixed documents should not be presented as a confident verdict at
    either end of the range.
    """
    label = band_for(score)
    if (
        window_stability is not None
        and window_stability >= STABILITY_FORCE_UNCERTAIN_STDEV
        and label is not Label.UNCERTAIN
    ):
        return Label.UNCERTAIN
    return label
