"""Normalization must preserve the author's text and report integrity risks."""

from __future__ import annotations

import pytest

from detection.normalization import (
    count_words,
    detect_scripts,
    inspect_integrity,
    normalize,
)


def test_display_text_is_returned_byte_for_byte() -> None:
    original = "Line one.\r\n\r\nLine  two — with  odd   spacing.\t"
    assert normalize(original).display_text == original


def test_punctuation_casing_and_paragraphs_survive_normalization() -> None:
    original = "First Paragraph! It's here.\n\nSecond one? Yes -- really."
    analysis = normalize(original).analysis_text
    assert "First Paragraph!" in analysis
    assert "It's here." in analysis
    assert analysis.count("\n\n") == 1
    assert "Yes -- really." in analysis


def test_crlf_is_canonicalised_without_losing_paragraph_breaks() -> None:
    analysis = normalize("A para.\r\n\r\nB para.").analysis_text
    assert analysis == "A para.\n\nB para."


def test_invisible_characters_are_flagged_and_removed() -> None:
    result = normalize("Hello​world and ­visible text here")
    assert "invisible_characters" in result.warning_codes
    assert "​" not in result.analysis_text
    assert "­" not in result.analysis_text


def test_homoglyphs_are_flagged_but_not_silently_rewritten() -> None:
    # Cyrillic 'а' inside an otherwise Latin word.
    result = normalize("This is аctually a homoglyph test with more words.")
    assert "homoglyph_risk" in result.warning_codes
    assert "mixed_scripts" in result.warning_codes
    assert "а" in result.analysis_text, "characters must not be silently replaced"


def test_excessive_whitespace_is_flagged_and_collapsed() -> None:
    result = normalize("Word" + " " * 12 + "spaced.\n\n\n\n\n\nNext.")
    assert "excessive_whitespace" in result.warning_codes
    assert "     " not in result.analysis_text
    assert "\n\n\n" not in result.analysis_text


def test_control_characters_are_flagged() -> None:
    assert "control_characters" in normalize("bad\x07bell here").warning_codes


def test_clean_text_produces_no_warnings() -> None:
    assert normalize("A perfectly ordinary sentence.\n\nAnd another.").warnings == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [("hello world", 2), ("  spaced   out  ", 2), ("", 0), ("one", 1)],
)
def test_word_counting(text: str, expected: int) -> None:
    assert count_words(text) == expected


def test_script_detection_identifies_mixed_writing_systems() -> None:
    assert "CYRILLIC" in detect_scripts("Hello дом")
    assert detect_scripts("Plain English") == {"LATIN"}


def test_integrity_inspection_is_pure() -> None:
    text = "Hello​world"
    assert inspect_integrity(text) == inspect_integrity(text)
