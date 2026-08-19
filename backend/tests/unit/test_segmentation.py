"""Segmentation must preserve order and never slice by character count."""

from __future__ import annotations

import pytest

from detection.segmentation import (
    build_windows,
    split_paragraphs,
    split_sentences,
    split_words,
)


def test_paragraph_ids_are_stable_and_ordered() -> None:
    paragraphs = split_paragraphs("One.\n\nTwo.\n\nThree.")
    assert [p.id for p in paragraphs] == ["p-000", "p-001", "p-002"]
    assert [p.index for p in paragraphs] == [0, 1, 2]
    assert [p.text for p in paragraphs] == ["One.", "Two.", "Three."]


def test_paragraph_ids_are_reproducible_for_identical_input() -> None:
    text = "Alpha.\n\nBeta."
    assert [p.id for p in split_paragraphs(text)] == [p.id for p in split_paragraphs(text)]


def test_blank_and_whitespace_only_paragraphs_are_dropped() -> None:
    assert len(split_paragraphs("One.\n\n   \n\n\n\nTwo.")) == 2


def test_single_newlines_do_not_split_paragraphs() -> None:
    paragraphs = split_paragraphs("Line one\nline two.\n\nSecond.")
    assert len(paragraphs) == 2
    assert "line two" in paragraphs[0].text


def test_sentence_splitting_handles_terminators() -> None:
    sentences = split_sentences("First. Second! Third? Fourth.")
    assert sentences == ["First.", "Second!", "Third?", "Fourth."]


def test_abbreviations_do_not_create_false_sentence_boundaries() -> None:
    sentences = split_sentences("Dr. Smith met Mrs. Jones today. They talked.")
    assert len(sentences) == 2
    assert sentences[0].startswith("Dr. Smith")


def test_words_exclude_digits_and_keep_internal_punctuation() -> None:
    assert split_words("The author's well-known 42 idea.") == [
        "the",
        "author's",
        "well-known",
        "idea",
    ]


class TestWindows:
    def test_windows_overlap_by_max_tokens_minus_stride(self) -> None:
        windows = build_windows(list(range(1000)), max_tokens=384, stride=320)
        assert [w.start for w in windows] == [0, 320, 640]
        assert windows[0].length == 384
        # Consecutive windows share the expected overlap.
        assert windows[1].start - windows[0].start == 320

    def test_no_window_exceeds_the_maximum(self) -> None:
        for window in build_windows(list(range(5000)), max_tokens=256, stride=200):
            assert window.length <= 256

    def test_all_tokens_are_covered(self) -> None:
        tokens = list(range(900))
        covered: set[int] = set()
        for window in build_windows(tokens, max_tokens=384, stride=320):
            covered.update(window.token_ids)
        assert covered == set(tokens)

    def test_short_input_yields_one_window(self) -> None:
        windows = build_windows(list(range(50)), max_tokens=384, stride=320)
        assert len(windows) == 1
        assert windows[0].length == 50

    def test_empty_input_yields_no_windows(self) -> None:
        assert build_windows([], max_tokens=384, stride=320) == []

    def test_windows_are_indexed_in_order(self) -> None:
        windows = build_windows(list(range(2000)), max_tokens=384, stride=320)
        assert [w.index for w in windows] == list(range(len(windows)))

    @pytest.mark.parametrize(
        ("max_tokens", "stride"),
        [(0, 10), (-1, 10), (384, 0), (384, -5), (100, 200)],
    )
    def test_invalid_window_parameters_are_rejected(self, max_tokens: int, stride: int) -> None:
        with pytest.raises(ValueError):
            build_windows(list(range(100)), max_tokens=max_tokens, stride=stride)
