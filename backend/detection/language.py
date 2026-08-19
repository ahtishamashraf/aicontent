"""Offline language detection.

``langdetect`` is a local port of Nakagawa/Ienaga's language profiles. It makes
no network calls, which keeps submitted text inside the deployment. The
detector is seeded so that identical input yields an identical verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from langdetect import DetectorFactory, LangDetectException, detect_langs

# Deterministic output for identical input.
DetectorFactory.seed = 0

#: The supported baseline. Documented in docs/DETECTION_METHODOLOGY.md.
SUPPORTED_LANGUAGE = "en"


@dataclass(frozen=True)
class LanguageVerdict:
    language: str
    confidence: float
    supported: bool


def detect_language(text: str, threshold: float) -> LanguageVerdict:
    """Return the dominant language and whether it clears ``threshold``.

    A detection failure (too short, no alphabetic content) is reported as an
    unsupported ``unknown`` verdict rather than being assumed English.
    """
    try:
        candidates = detect_langs(text)
    except LangDetectException:
        return LanguageVerdict(language="unknown", confidence=0.0, supported=False)

    if not candidates:
        return LanguageVerdict(language="unknown", confidence=0.0, supported=False)

    english = next((c for c in candidates if c.lang == SUPPORTED_LANGUAGE), None)
    english_confidence = float(english.prob) if english else 0.0
    top = candidates[0]

    return LanguageVerdict(
        language=top.lang,
        confidence=english_confidence,
        supported=english_confidence >= threshold,
    )
