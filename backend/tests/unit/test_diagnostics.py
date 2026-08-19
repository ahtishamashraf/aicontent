"""Deterministic diagnostics describe context; they never replace the model."""

from __future__ import annotations

from detection.diagnostics import (
    DIAGNOSTICS_VERSION,
    compute_diagnostics,
    consecutive_structural_similarity,
    moving_average_ttr,
    paragraph_length_stats,
    punctuation_distribution,
    repeated_ngram_rate,
    repeated_sentence_openings,
    sentence_length_stats,
    transition_phrase_density,
)
from detection.segmentation import split_words
from detection.wordlists import WORDLIST_VERSION

UNIFORM = (
    "The system provides benefits. The system delivers improvements. "
    "The system offers advantages. The system enables progress."
)
VARIED = (
    "Rain. It had been threatening since dawn, and when it finally arrived it "
    "turned the lane into a shallow river that swallowed both kerbs. I forgot my coat."
)


class TestSentenceStats:
    def test_mean_and_stdev_for_known_input(self) -> None:
        stats = sentence_length_stats("One two three. Four five six.")
        assert stats.count == 2
        assert stats.mean == 3.0
        assert stats.stdev == 0.0
        assert stats.coefficient_of_variation == 0.0

    def test_coefficient_of_variation_rises_with_variation(self) -> None:
        assert (
            sentence_length_stats(VARIED).coefficient_of_variation
            > sentence_length_stats(UNIFORM).coefficient_of_variation
        )

    def test_empty_text_is_safe(self) -> None:
        stats = sentence_length_stats("")
        assert stats.count == 0 and stats.mean == 0.0


class TestParagraphStats:
    def test_paragraph_variation_is_measured(self) -> None:
        stats = paragraph_length_stats("one two three four.\n\nfive.")
        assert stats.count == 2
        assert stats.coefficient_of_variation > 0


class TestLexical:
    def test_mattr_is_one_when_every_word_is_unique(self) -> None:
        assert moving_average_ttr(["a", "b", "c", "d"]) == 1.0

    def test_mattr_falls_with_repetition(self) -> None:
        assert moving_average_ttr(["a"] * 10) == 0.1

    def test_mattr_is_length_stable_unlike_raw_ttr(self) -> None:
        # Same generator, different lengths: MATTR should stay close.
        short = moving_average_ttr([f"w{i % 60}" for i in range(120)])
        long = moving_average_ttr([f"w{i % 60}" for i in range(600)])
        assert abs(short - long) < 0.1

    def test_empty_input_is_safe(self) -> None:
        assert moving_average_ttr([]) == 0.0


class TestNgrams:
    def test_no_repeats_scores_zero(self) -> None:
        assert repeated_ngram_rate(["a", "b", "c", "d"], 2) == 0.0

    def test_repeats_are_detected_at_each_order(self) -> None:
        words = split_words(UNIFORM)
        assert repeated_ngram_rate(words, 2) > 0

    def test_input_shorter_than_n_is_safe(self) -> None:
        assert repeated_ngram_rate(["a"], 4) == 0.0


class TestOpeningsAndStructure:
    def test_repeated_openings_are_detected(self) -> None:
        assert repeated_sentence_openings(UNIFORM) > 0.5

    def test_varied_openings_score_low(self) -> None:
        assert repeated_sentence_openings(VARIED) == 0.0

    def test_single_sentence_is_safe(self) -> None:
        assert repeated_sentence_openings("Only one sentence here.") == 0.0

    def test_uniform_prose_is_structurally_more_similar(self) -> None:
        assert consecutive_structural_similarity(UNIFORM) > consecutive_structural_similarity(
            VARIED
        )


class TestDistributions:
    def test_punctuation_is_reported_per_1000_characters(self) -> None:
        distribution = punctuation_distribution("a, b, c." + "x" * 992)
        assert distribution[","] == 2.0
        assert distribution["."] == 1.0

    def test_empty_text_yields_zeroed_distribution(self) -> None:
        assert all(v == 0.0 for v in punctuation_distribution("").values())

    def test_transition_density_counts_versioned_phrases(self) -> None:
        assert transition_phrase_density("However, the plan changed.") > 0
        assert transition_phrase_density("The cat sat on the mat.") == 0.0


class TestReport:
    def test_report_is_deterministic(self) -> None:
        assert compute_diagnostics(VARIED).to_dict() == compute_diagnostics(VARIED).to_dict()

    def test_report_declares_its_versions(self) -> None:
        report = compute_diagnostics(VARIED)
        assert report.version == DIAGNOSTICS_VERSION
        assert report.wordlist_version == WORDLIST_VERSION

    def test_report_carries_no_score_field(self) -> None:
        # Diagnostics must not smuggle in a competing classification.
        keys = compute_diagnostics(VARIED).to_dict()
        assert "score" not in keys
        assert "label" not in keys

    def test_empty_text_produces_a_complete_report(self) -> None:
        report = compute_diagnostics("").to_dict()
        assert report["moving_average_ttr"] == 0.0
        assert report["sentence_lengths"]["count"] == 0
