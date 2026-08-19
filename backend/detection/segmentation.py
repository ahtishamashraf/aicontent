"""Paragraph, sentence, and model-window segmentation.

Windows are always built from tokenizer output, never by slicing characters:
a character slice can split a word or a multi-byte grapheme and silently
changes what the model sees.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

#: Paragraphs are separated by a blank line, matching how authors write.
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

#: Sentence terminator followed by whitespace and a capital/quote/digit.
#: Common abbreviations are protected so they do not create false boundaries.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]*[A-Z0-9])")

_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "sr",
    "jr",
    "st",
    "vs",
    "etc",
    "eg",
    "ie",
    "cf",
    "al",
    "inc",
    "ltd",
    "co",
    "fig",
    "no",
    "vol",
    "pp",
    "ed",
}

# The character class deliberately includes the typographic apostrophe so that
# a possessive written with a curly quote stays a single word.
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)  # noqa: RUF001


@dataclass(frozen=True)
class Paragraph:
    """A paragraph with a stable, order-preserving identifier."""

    index: int
    text: str

    @property
    def id(self) -> str:
        """Stable identifier derived from position, e.g. ``p-003``."""
        return f"p-{self.index:03d}"

    @property
    def words(self) -> int:
        return len(self.text.split())

    @property
    def characters(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class TokenWindow:
    """A contiguous run of token ids handed to the model."""

    index: int
    token_ids: Sequence[int]
    start: int

    @property
    def length(self) -> int:
        return len(self.token_ids)


def split_paragraphs(text: str) -> list[Paragraph]:
    """Split ``text`` on blank lines, preserving order and dropping empties."""
    chunks = [chunk.strip() for chunk in _PARAGRAPH_SPLIT.split(text)]
    return [Paragraph(index=i, text=chunk) for i, chunk in enumerate(c for c in chunks if c)]


def _ends_with_abbreviation(fragment: str) -> bool:
    match = re.search(r"([A-Za-z]+)\.$", fragment.strip())
    return match is not None and match.group(1).lower() in _ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences, re-joining abbreviation false splits."""
    raw = _SENTENCE_SPLIT.split(text.replace("\n", " "))
    sentences: list[str] = []
    for fragment in raw:
        fragment = fragment.strip()
        if not fragment:
            continue
        if sentences and _ends_with_abbreviation(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {fragment}"
        else:
            sentences.append(fragment)
    return sentences


def split_words(text: str) -> list[str]:
    """Alphabetic word tokens, lowercased, for lexical diagnostics."""
    return [m.group(0).lower() for m in _WORD.finditer(text)]


def build_windows(token_ids: Sequence[int], max_tokens: int, stride: int) -> list[TokenWindow]:
    """Split ``token_ids`` into overlapping windows of at most ``max_tokens``.

    ``stride`` is the advance between window starts, so the overlap is
    ``max_tokens - stride`` tokens. A trailing window shorter than the stride is
    merged into its predecessor rather than being scored on a sliver of text.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not 0 < stride <= max_tokens:
        raise ValueError("stride must be positive and no larger than max_tokens")
    if not token_ids:
        return []

    windows: list[TokenWindow] = []
    start = 0
    index = 0
    total = len(token_ids)

    while start < total:
        end = min(start + max_tokens, total)
        windows.append(TokenWindow(index=index, token_ids=token_ids[start:end], start=start))
        if end >= total:
            break
        start += stride
        index += 1

    # Avoid a final window that is mostly overlap with no new information.
    if len(windows) > 1 and windows[-1].length < max(1, stride // 4):
        windows.pop()

    return windows
