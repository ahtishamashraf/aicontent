"""Language routing is offline and English-only by design."""

from __future__ import annotations

from detection.language import SUPPORTED_LANGUAGE, detect_language

ENGLISH = (
    "The committee reviewed the proposal carefully and concluded that the revised "
    "timeline remained achievable given the staffing available this quarter."
)
FRENCH = (
    "Le comite a examine la proposition avec attention et a conclu que le calendrier "
    "revise restait realisable compte tenu des effectifs disponibles ce trimestre."
)
GERMAN = (
    "Der Ausschuss hat den Vorschlag sorgfaeltig geprueft und ist zu dem Schluss "
    "gekommen, dass der ueberarbeitete Zeitplan weiterhin machbar bleibt."
)


def test_english_is_supported() -> None:
    verdict = detect_language(ENGLISH, 0.60)
    assert verdict.language == SUPPORTED_LANGUAGE
    assert verdict.supported is True
    assert verdict.confidence >= 0.60


def test_french_is_not_supported() -> None:
    verdict = detect_language(FRENCH, 0.60)
    assert verdict.supported is False
    assert verdict.language != SUPPORTED_LANGUAGE


def test_german_is_not_supported() -> None:
    assert detect_language(GERMAN, 0.60).supported is False


def test_undetectable_input_is_not_assumed_to_be_english() -> None:
    verdict = detect_language("!!! ??? ###", 0.60)
    assert verdict.supported is False
    assert verdict.language == "unknown"
    assert verdict.confidence == 0.0


def test_threshold_is_honoured() -> None:
    # An impossible threshold must reject even clean English.
    assert detect_language(ENGLISH, 1.01).supported is False


def test_detection_is_deterministic() -> None:
    assert detect_language(ENGLISH, 0.60) == detect_language(ENGLISH, 0.60)
