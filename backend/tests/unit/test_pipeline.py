"""End-to-end behaviour of the analysis pipeline with the fake detector."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from detection.calibration import Label, Reliability
from detection.engines.fake import FakeProvider
from detection.pipeline import InputRejected, analyse


def _words(count: int) -> str:
    """Deterministic English-looking filler of a given word count."""
    base = (
        "the committee reviewed several revised proposals during the session and "
        "members raised concerns about the delivery timeline before the recess "
    )
    words = (base * (count // 16 + 2)).split()[:count]
    return " ".join(words) + "."


class TestLengthGates:
    def test_below_minimum_returns_insufficient_without_scoring(
        self, provider: FakeProvider, settings: Settings
    ) -> None:
        result = analyse(_words(40), provider, settings)
        assert result.label == Label.INSUFFICIENT.value
        assert result.public_score is None
        assert result.raw_model_score is None
        assert result.reliability == Reliability.INSUFFICIENT.value
        assert result.reliability_reasons

    def test_at_minimum_is_analysed(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        assert result.public_score is not None
        assert result.label != Label.INSUFFICIENT.value

    def test_between_80_and_149_words_is_marked_low_reliability(
        self, provider: FakeProvider, settings: Settings
    ) -> None:
        result = analyse(_words(100), provider, settings)
        assert result.public_score is not None
        assert result.reliability == Reliability.LOW.value
        assert any("150" in reason for reason in result.reliability_reasons)

    def test_150_words_or_more_is_not_penalised_for_length(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        assert result.word_count >= 150
        assert not any("words were analysed" in r for r in result.reliability_reasons)


class TestRejections:
    @pytest.mark.parametrize(
        ("text", "code"),
        [
            ("", "empty_input"),
            ("     \n\n  ", "empty_input"),
            ("hello\x00world", "binary_input"),
            ("spam " * 500, "repetitive_input"),
            ("x" * 1200, "pathological_input"),
        ],
    )
    def test_pathological_input_is_rejected(
        self, provider: FakeProvider, settings: Settings, text: str, code: str
    ) -> None:
        with pytest.raises(InputRejected) as excinfo:
            analyse(text, provider, settings)
        assert excinfo.value.code == code

    def test_oversized_text_is_rejected(self, provider: FakeProvider, settings: Settings) -> None:
        with pytest.raises(InputRejected) as excinfo:
            analyse(_words(settings.max_words + 50), provider, settings)
        assert excinfo.value.code == "too_long"

    def test_character_limit_is_enforced(self, provider: FakeProvider, settings: Settings) -> None:
        with pytest.raises(InputRejected) as excinfo:
            analyse("word " * (settings.max_characters // 2), provider, settings)
        assert excinfo.value.code == "too_long"


class TestLanguageRouting:
    def test_non_english_returns_unsupported_language(
        self, provider: FakeProvider, settings: Settings
    ) -> None:
        french = (
            "Le comite a examine la proposition avec beaucoup d attention pendant la "
            "session de mars et plusieurs membres ont exprime des inquietudes au sujet "
            "du calendrier de livraison propose par la direction generale du service. "
            "La question du recrutement reste egalement ouverte car deux postes sont "
            "vacants depuis le mois de janvier dernier et la charge de travail repose "
            "desormais sur une equipe beaucoup plus reduite que prevu initialement. "
            "Le president a donc accepte de faire circuler un nouveau calendrier."
        )
        result = analyse(french, provider, settings)
        assert result.label == Label.UNSUPPORTED_LANGUAGE.value
        assert result.public_score is None
        assert result.detected_language != "en"

    def test_english_is_accepted(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        assert result.detected_language == "en"
        assert result.label != Label.UNSUPPORTED_LANGUAGE.value


class TestResultShape:
    def test_raw_and_public_scores_are_stored_separately(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        assert 0.0 <= result.raw_model_score <= 1.0
        assert 0 <= result.public_score <= 100
        assert result.raw_model_score != result.public_score

    def test_provenance_is_recorded(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        assert result.calibration_version
        assert result.detector_version
        assert result.model_metadata["backend"] == "fake"

    def test_diagnostics_are_included_with_window_consistency(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        assert result.diagnostics["window_consistency"] is not None
        assert "moving_average_ttr" in result.diagnostics

    def test_analysis_is_deterministic(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        first = analyse(english_text, provider, settings)
        second = analyse(english_text, provider, settings)
        assert first.public_score == second.public_score
        assert first.window_scores == second.window_scores

    def test_integrity_warnings_are_surfaced(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text.replace("The", "Th​e", 1), provider, settings)
        codes = [w["code"] for w in result.integrity_warnings]
        assert "invisible_characters" in codes


class TestParagraphAttribution:
    def test_paragraph_ids_are_stable_and_ordered(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        assert [s.id for s in result.segments] == [
            f"p-{i:03d}" for i in range(len(result.segments))
        ]

    def test_short_paragraphs_are_not_given_false_precision(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(f"{english_text}\n\nOK.", provider, settings)
        final = result.segments[-1]
        assert final.too_short is True
        assert final.public_score is None
        assert final.label is None

    def test_paragraph_scores_come_from_real_window_scores(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings)
        scored = [s for s in result.segments if s.public_score is not None]
        assert scored, "expected at least one scored paragraph"
        for segment in scored:
            assert 0 <= segment.public_score <= 100
            assert segment.raw_score is not None
            assert segment.public_score == round(segment.raw_score * 100)

    def test_paragraph_text_can_be_withheld(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        result = analyse(english_text, provider, settings, include_paragraph_text=False)
        assert all(segment.text == "" for segment in result.segments)

    def test_very_short_paragraphs_are_never_scored_via_borrowed_context(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        # A heading beside a long paragraph must not inherit its neighbour's score.
        result = analyse(f"Summary\n\n{english_text}", provider, settings)
        heading = result.segments[0]
        assert heading.word_count == 1
        assert heading.too_short is True
        assert heading.public_score is None
        assert heading.grouped_with_context is False

    def test_medium_paragraphs_are_scored_with_context_and_flagged(
        self, provider: FakeProvider, settings: Settings, english_text: str
    ) -> None:
        medium = " ".join(["the revised schedule was circulated before the meeting"] * 4)
        result = analyse(f"{english_text}\n\n{medium}", provider, settings)
        final = result.segments[-1]
        assert 15 <= final.word_count < 40
        assert final.grouped_with_context is True
        assert final.public_score is not None
