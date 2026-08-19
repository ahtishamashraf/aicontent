"""End-to-end analysis pipeline.

Orchestrates normalization, language routing, length gating, model scoring,
aggregation, calibration, paragraph attribution, and diagnostics into one
deterministic result object. The pipeline holds no database or HTTP concerns so
it can be exercised directly by unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from detection.aggregation import Aggregate, aggregate_windows
from detection.calibration import (
    ABSOLUTE_MIN_PARAGRAPH_WORDS,
    CALIBRATION_VERSION,
    DETECTOR_VERSION,
    MIN_PARAGRAPH_WORDS_FOR_SCORE,
    Label,
    Reliability,
    apply_stability_override,
    assess_reliability,
    calibrate,
)
from detection.diagnostics import compute_diagnostics
from detection.engines.base import DetectorProvider
from detection.language import detect_language
from detection.normalization import IntegrityWarning, normalize
from detection.segmentation import Paragraph, split_paragraphs


class InputRejected(Exception):
    """Raised when input cannot be analysed at all. ``code`` is client-safe."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class SegmentResult:
    id: str
    index: int
    text: str
    word_count: int
    character_count: int
    raw_score: float | None = None
    public_score: int | None = None
    label: str | None = None
    too_short: bool = False
    grouped_with_context: bool = False


@dataclass
class AnalysisResult:
    label: str
    public_score: int | None
    raw_model_score: float | None
    reliability: str
    reliability_reasons: list[str]
    word_count: int
    character_count: int
    paragraph_count: int
    segments: list[SegmentResult] = field(default_factory=list)
    integrity_warnings: list[dict[str, str]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    window_stability: float | None = None
    window_scores: list[float] = field(default_factory=list)
    detected_language: str | None = None
    language_confidence: float | None = None
    model_metadata: dict[str, Any] = field(default_factory=dict)
    calibration_version: str = CALIBRATION_VERSION
    detector_version: str = DETECTOR_VERSION


def _warnings_payload(warnings: list[IntegrityWarning]) -> list[dict[str, str]]:
    return [{"code": w.code, "message": w.message} for w in warnings]


def _validate_size(text: str, settings: Settings) -> None:
    """Reject empty, oversized, and pathological input before any inference."""
    if not text or not text.strip():
        raise InputRejected("empty_input", "No text was submitted.")

    if "\x00" in text:
        raise InputRejected("binary_input", "The submission contains binary data.")

    if len(text) > settings.max_characters:
        raise InputRejected(
            "too_long",
            f"The submission exceeds the {settings.max_characters:,}-character limit.",
        )

    words = text.split()
    if len(words) > settings.max_words:
        raise InputRejected(
            "too_long",
            f"The submission exceeds the {settings.max_words:,}-word limit.",
        )

    # Pathological repetition: a tiny vocabulary repeated to fill the limit is a
    # cheap way to make inference expensive without being real writing.
    if len(words) >= 200:
        unique_ratio = len({w.lower() for w in words}) / len(words)
        if unique_ratio < 0.02:
            raise InputRejected(
                "repetitive_input",
                "The submission is too repetitive to analyse meaningfully.",
            )

    # A single unbroken token of extreme length is not natural writing and can
    # blow up tokenization cost.
    if any(len(word) > 1000 for word in words):
        raise InputRejected(
            "pathological_input",
            "The submission contains an unreasonably long unbroken token.",
        )


def _score_paragraphs(
    paragraphs: list[Paragraph],
    provider: DetectorProvider,
    document_stability: float | None,
) -> list[SegmentResult]:
    """Score paragraphs that carry enough evidence; mark the rest honestly.

    A short paragraph is grouped with its neighbour for scoring context rather
    than being given a precise-looking number it cannot support.
    """
    results: list[SegmentResult] = []

    for position, paragraph in enumerate(paragraphs):
        segment = SegmentResult(
            id=paragraph.id,
            index=paragraph.index,
            text=paragraph.text,
            word_count=paragraph.words,
            character_count=paragraph.characters,
        )

        if paragraph.words < ABSOLUTE_MIN_PARAGRAPH_WORDS:
            # Too short to carry evidence of its own. Borrowed context would
            # score the neighbours, not this paragraph.
            segment.too_short = True
            results.append(segment)
            continue

        if paragraph.words >= MIN_PARAGRAPH_WORDS_FOR_SCORE:
            scoring_text = paragraph.text
        else:
            # Borrow context from neighbours so a heading or one-line paragraph
            # is interpreted in situ instead of in isolation.
            neighbours = [
                paragraphs[i].text
                for i in (position - 1, position, position + 1)
                if 0 <= i < len(paragraphs)
            ]
            combined = "\n\n".join(neighbours)
            if len(combined.split()) < MIN_PARAGRAPH_WORDS_FOR_SCORE:
                segment.too_short = True
                results.append(segment)
                continue
            scoring_text = combined
            segment.grouped_with_context = True

        window_scores = provider.score_text(scoring_text)
        if not window_scores.scores:
            segment.too_short = True
            results.append(segment)
            continue

        aggregate = aggregate_windows(window_scores.scores, window_scores.token_weights)
        segment.raw_score = aggregate.raw_score
        segment.public_score = calibrate(aggregate.raw_score)
        segment.label = apply_stability_override(segment.public_score, document_stability).value
        results.append(segment)

    return results


def analyse(
    text: str,
    provider: DetectorProvider,
    settings: Settings,
    *,
    include_paragraph_text: bool = True,
) -> AnalysisResult:
    """Run the full analysis for ``text``.

    Raises :class:`InputRejected` when the submission cannot be analysed.
    """
    _validate_size(text, settings)

    normalized = normalize(text)
    analysis_text = normalized.analysis_text
    words = analysis_text.split()
    word_count = len(words)
    paragraphs = split_paragraphs(analysis_text)

    base = AnalysisResult(
        label=Label.INSUFFICIENT.value,
        public_score=None,
        raw_model_score=None,
        reliability=Reliability.INSUFFICIENT.value,
        reliability_reasons=[],
        word_count=word_count,
        character_count=len(normalized.display_text),
        paragraph_count=len(paragraphs),
        integrity_warnings=_warnings_payload(normalized.warnings),
        detected_language=None,
        language_confidence=None,
    )

    # --- Length gate: cheapest rejection first, before any inference ---------
    if word_count < settings.min_words:
        base.reliability_reasons = [
            f"At least {settings.min_words} words are required; {word_count} were submitted."
        ]
        return base

    # --- Language routing ----------------------------------------------------
    verdict = detect_language(analysis_text, settings.english_confidence_threshold)
    base.detected_language = verdict.language
    base.language_confidence = round(verdict.confidence, 4)
    if not verdict.supported:
        base.label = Label.UNSUPPORTED_LANGUAGE.value
        base.reliability = Reliability.INSUFFICIENT.value
        base.reliability_reasons = [
            f"This analyser is validated for English only. Detected language: {verdict.language}."
        ]
        return base

    # --- Model scoring -------------------------------------------------------
    window_scores = provider.score_text(analysis_text)
    if not window_scores.scores:
        base.reliability_reasons = ["The text produced no analysable content."]
        return base

    aggregate: Aggregate = aggregate_windows(window_scores.scores, window_scores.token_weights)
    public_score = calibrate(aggregate.raw_score)

    assessment = assess_reliability(
        word_count=word_count,
        window_stability=aggregate.stability,
        min_words=settings.min_words,
        low_reliability_words=settings.low_reliability_words,
        integrity_warning_codes=normalized.warning_codes,
        window_count=aggregate.window_count,
    )

    diagnostics = compute_diagnostics(analysis_text)
    diagnostics.window_consistency = aggregate.consistency

    segments = _score_paragraphs(paragraphs, provider, aggregate.stability)
    if not include_paragraph_text:
        for segment in segments:
            segment.text = ""

    base.label = apply_stability_override(public_score, aggregate.stability).value
    base.public_score = public_score
    base.raw_model_score = aggregate.raw_score
    base.reliability = assessment.level.value
    base.reliability_reasons = assessment.reasons
    base.window_stability = aggregate.stability
    base.window_scores = aggregate.window_scores
    base.diagnostics = diagnostics.to_dict()
    base.segments = segments
    base.model_metadata = provider.metadata()
    return base
