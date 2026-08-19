"""Centralised product identity, limits, and disclaimers.

The frontend reads these from ``/api/v1/config`` rather than hard-coding them,
so the product name, limits, and thresholds have exactly one source of truth.
"""

from __future__ import annotations

PRODUCT_NAME = "OriginLens"
TAGLINE = "Evidence-based signals about how writing was produced — never a verdict on who wrote it."
SUPPORT_EMAIL = "support@originlens.local"

#: Shown on every result, including printed and exported output.
DISCLAIMERS: tuple[str, ...] = (
    "This score is an estimate of stylistic patterns, not proof of authorship.",
    "Edited, paraphrased, translated, formulaic, or highly technical writing can "
    "be misclassified in either direction.",
    "The analyser is validated for English only.",
    "Do not make a consequential decision about a person from this result alone. "
    "Use human judgement and additional evidence.",
)
