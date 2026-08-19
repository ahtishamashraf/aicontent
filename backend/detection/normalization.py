"""Text normalization and integrity inspection.

Two representations exist for every submission:

``display_text``
    The submitter's bytes, preserved exactly. Punctuation, casing, and
    paragraph boundaries are untouched. This is what is shown back and what is
    encrypted at rest when the submitter opts into storage.

``analysis_text``
    A separate normalized copy used for tokenization and statistics. Invisible
    formatting characters are removed and line endings are canonicalised, but
    words, punctuation, casing, and paragraph structure are preserved so that
    diagnostics measure the author's writing rather than an artefact of
    cleaning.

Integrity findings are reported as warnings; they never silently alter the
public score.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: Zero-width and bidirectional control characters used to evade detection or
#: to smuggle markers into text.
INVISIBLE_CHARS = {
    "​": "zero-width space",
    "‌": "zero-width non-joiner",
    "‍": "zero-width joiner",
    "‎": "left-to-right mark",
    "‏": "right-to-left mark",
    "⁠": "word joiner",
    "﻿": "byte-order mark",
    "­": "soft hyphen",
    "‪": "bidirectional embedding",
    "‫": "bidirectional embedding",
    "‬": "bidirectional override",
    "‭": "bidirectional override",
    "‮": "bidirectional override",
}

#: Latin look-alikes drawn from Cyrillic and Greek. Presence of these inside
#: otherwise-Latin words is a homoglyph signal.
HOMOGLYPHS = {
    "а": "a",
    "е": "e",
    "о": "o",
    "р": "p",
    "с": "c",
    "у": "y",
    "х": "x",
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "Х": "X",
    "ο": "o",
    "α": "a",
    "ε": "e",
    "Α": "A",
    "Β": "B",
    "Ε": "E",
    "Ο": "O",
}

#: Scripts that are unremarkable in English prose.
_NEUTRAL_SCRIPTS = {"COMMON", "INHERITED", "LATIN"}

_WHITESPACE_RUN = re.compile(r"[ \t  -   　]{4,}")
_BLANKLINE_RUN = re.compile(r"(?:\r?\n[ \t]*){4,}")
_HORIZONTAL_WS = re.compile(r"[ \t  -   　]+")


@dataclass(frozen=True)
class IntegrityWarning:
    """A content-integrity finding. ``detail`` never contains submitted text."""

    code: str
    message: str


@dataclass
class NormalizedText:
    display_text: str
    analysis_text: str
    warnings: list[IntegrityWarning] = field(default_factory=list)

    @property
    def warning_codes(self) -> list[str]:
        return [w.code for w in self.warnings]


def _script_of(char: str) -> str:
    """Best-effort Unicode script name derived from the character name."""
    try:
        name = unicodedata.name(char)
    except ValueError:
        return "UNKNOWN"
    for script in (
        "LATIN",
        "CYRILLIC",
        "GREEK",
        "ARABIC",
        "HEBREW",
        "HAN",
        "HIRAGANA",
        "KATAKANA",
        "HANGUL",
        "DEVANAGARI",
        "THAI",
        "CJK",
    ):
        if name.startswith(script) or f" {script} " in name:
            return "HAN" if script == "CJK" else script
    return "COMMON"


def detect_scripts(text: str) -> set[str]:
    """Return the set of non-neutral scripts present in ``text``."""
    scripts: set[str] = set()
    for char in text:
        if char.isalpha():
            scripts.add(_script_of(char))
    return scripts


def inspect_integrity(text: str) -> list[IntegrityWarning]:
    """Report invisible characters, mixed scripts, homoglyphs, and whitespace."""
    warnings: list[IntegrityWarning] = []

    found_invisible = sorted({INVISIBLE_CHARS[c] for c in text if c in INVISIBLE_CHARS})
    if found_invisible:
        warnings.append(
            IntegrityWarning(
                "invisible_characters",
                "Invisible formatting characters were found and removed before "
                f"analysis ({', '.join(found_invisible)}).",
            )
        )

    scripts = detect_scripts(text) - _NEUTRAL_SCRIPTS
    if scripts:
        warnings.append(
            IntegrityWarning(
                "mixed_scripts",
                "The text mixes Latin characters with other writing systems "
                f"({', '.join(sorted(scripts))}). This can be legitimate.",
            )
        )

    homoglyph_count = sum(1 for c in text if c in HOMOGLYPHS)
    if homoglyph_count:
        warnings.append(
            IntegrityWarning(
                "homoglyph_risk",
                f"{homoglyph_count} character(s) resemble Latin letters but come "
                "from another script, which can indicate evasion.",
            )
        )

    if _WHITESPACE_RUN.search(text) or _BLANKLINE_RUN.search(text):
        warnings.append(
            IntegrityWarning(
                "excessive_whitespace",
                "Unusually long runs of whitespace or blank lines were collapsed for analysis.",
            )
        )

    if any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in text):
        warnings.append(
            IntegrityWarning(
                "control_characters",
                "Control characters were found and removed before analysis.",
            )
        )

    return warnings


def normalize(text: str) -> NormalizedText:
    """Produce the analysis copy and integrity warnings for ``text``.

    The display copy is returned unchanged.
    """
    warnings = inspect_integrity(text)

    # NFC keeps composed forms stable without altering the author's words.
    analysis = unicodedata.normalize("NFC", text)
    analysis = analysis.replace("\r\n", "\n").replace("\r", "\n")
    analysis = "".join(c for c in analysis if c not in INVISIBLE_CHARS)
    analysis = "".join(c for c in analysis if unicodedata.category(c) != "Cc" or c in "\n\t")
    # Collapse runs of horizontal whitespace but keep single spaces and newlines,
    # so sentence and paragraph structure survives intact.
    analysis = _HORIZONTAL_WS.sub(" ", analysis)
    # Cap consecutive blank lines at one, preserving paragraph boundaries.
    analysis = re.sub(r"\n{3,}", "\n\n", analysis)
    analysis = "\n".join(line.rstrip() for line in analysis.split("\n")).strip()

    return NormalizedText(display_text=text, analysis_text=analysis, warnings=warnings)


def count_words(text: str) -> int:
    """Whitespace-delimited word count over the analysis copy."""
    return len(text.split())
