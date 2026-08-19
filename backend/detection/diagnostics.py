"""Neutral, deterministic text statistics.

These diagnostics exist to explain *context and reliability* to a reader. They
are reported alongside the classifier output and are never blended into the
public score: there is no validated weighting that would justify doing so, and
inventing one would be pseudo-science dressed as a measurement.

Every function is pure and deterministic.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from typing import Any

from detection.segmentation import split_paragraphs, split_sentences, split_words
from detection.wordlists import FUNCTION_WORDS, TRANSITION_PHRASES, WORDLIST_VERSION

#: Bump when a diagnostic's definition changes.
DIAGNOSTICS_VERSION = "1.0.0"

#: Window size for the moving-average type-token ratio.
MATTR_WINDOW = 50

#: Punctuation marks whose distribution is reported.
TRACKED_PUNCTUATION = (",", ".", ";", ":", "—", "–", "-", "!", "?", "'", '"', "(", ")")


def _safe_mean(values: list[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _safe_stdev(values: list[float]) -> float:
    return float(statistics.stdev(values)) if len(values) > 1 else 0.0


def _coefficient_of_variation(values: list[float]) -> float:
    """Standard deviation relative to the mean; 0.0 when the mean is 0."""
    mean = _safe_mean(values)
    if mean == 0:
        return 0.0
    return _safe_stdev(values) / mean


@dataclass
class LengthStats:
    count: int = 0
    mean: float = 0.0
    stdev: float = 0.0
    coefficient_of_variation: float = 0.0
    minimum: int = 0
    maximum: int = 0


def sentence_length_stats(text: str) -> LengthStats:
    """Word-count statistics across sentences."""
    lengths = [float(len(s.split())) for s in split_sentences(text)]
    if not lengths:
        return LengthStats()
    return LengthStats(
        count=len(lengths),
        mean=round(_safe_mean(lengths), 4),
        stdev=round(_safe_stdev(lengths), 4),
        coefficient_of_variation=round(_coefficient_of_variation(lengths), 4),
        minimum=int(min(lengths)),
        maximum=int(max(lengths)),
    )


def paragraph_length_stats(text: str) -> LengthStats:
    """Word-count statistics across paragraphs."""
    lengths = [float(p.words) for p in split_paragraphs(text)]
    if not lengths:
        return LengthStats()
    return LengthStats(
        count=len(lengths),
        mean=round(_safe_mean(lengths), 4),
        stdev=round(_safe_stdev(lengths), 4),
        coefficient_of_variation=round(_coefficient_of_variation(lengths), 4),
        minimum=int(min(lengths)),
        maximum=int(max(lengths)),
    )


def moving_average_ttr(words: list[str], window: int = MATTR_WINDOW) -> float:
    """Moving-average type-token ratio.

    MATTR is used instead of a raw type-token ratio because raw TTR falls as
    length grows, which would make it a proxy for word count rather than for
    lexical variety. When the text is shorter than one window, the plain ratio
    over the whole text is returned.
    """
    if not words:
        return 0.0
    if len(words) <= window:
        return round(len(set(words)) / len(words), 4)

    ratios = [len(set(words[i : i + window])) / window for i in range(len(words) - window + 1)]
    return round(_safe_mean(ratios), 4)


def repeated_ngram_rate(words: list[str], n: int) -> float:
    """Share of ``n``-gram occurrences that are repeats of an earlier one.

    0.0 means every n-gram is unique; higher values mean more repetition.
    """
    if len(words) < n:
        return 0.0
    ngrams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
    counts = Counter(ngrams)
    repeats = sum(count - 1 for count in counts.values() if count > 1)
    return round(repeats / len(ngrams), 4)


def repeated_sentence_openings(text: str, opening_words: int = 2) -> float:
    """Share of sentences whose opening ``opening_words`` repeat an earlier one."""
    sentences = split_sentences(text)
    if len(sentences) < 2:
        return 0.0
    openings = [" ".join(split_words(s)[:opening_words]) for s in sentences if split_words(s)]
    if not openings:
        return 0.0
    counts = Counter(openings)
    repeats = sum(count - 1 for count in counts.values() if count > 1)
    return round(repeats / len(openings), 4)


def punctuation_distribution(text: str) -> dict[str, float]:
    """Occurrences of each tracked mark per 1,000 characters."""
    if not text:
        return {mark: 0.0 for mark in TRACKED_PUNCTUATION}
    scale = 1000.0 / len(text)
    return {mark: round(text.count(mark) * scale, 4) for mark in TRACKED_PUNCTUATION}


def function_word_distribution(words: list[str], top_n: int = 15) -> dict[str, float]:
    """Relative frequency of the most common function words."""
    if not words:
        return {}
    counts = Counter(w for w in words if w in FUNCTION_WORDS)
    total = len(words)
    return {word: round(count / total, 5) for word, count in counts.most_common(top_n)}


def transition_phrase_density(text: str) -> float:
    """Transition phrases per 100 words, using the versioned list."""
    words = split_words(text)
    if not words:
        return 0.0
    lowered = " ".join(words)
    hits = 0
    for phrase in TRANSITION_PHRASES:
        if " " in phrase:
            hits += lowered.count(phrase)
        else:
            hits += sum(1 for w in words if w == phrase)
    return round(hits * 100.0 / len(words), 4)


def _structural_signature(sentence: str) -> tuple[int, int, float]:
    """Coarse shape of a sentence: length, clause count, function-word share."""
    words = split_words(sentence)
    if not words:
        return (0, 0, 0.0)
    clauses = 1 + sentence.count(",") + sentence.count(";")
    function_share = sum(1 for w in words if w in FUNCTION_WORDS) / len(words)
    return (len(words), clauses, function_share)


def consecutive_structural_similarity(text: str) -> float:
    """Mean similarity between the shapes of adjacent sentences, in [0, 1].

    Sentences that are consistently the same length, clause count, and
    function-word density score higher. This describes rhythm; it is not
    evidence of authorship on its own.
    """
    sentences = split_sentences(text)
    if len(sentences) < 2:
        return 0.0

    signatures = [_structural_signature(s) for s in sentences]
    similarities: list[float] = []
    for left, right in pairwise(signatures):
        length_sim = 1.0 - abs(left[0] - right[0]) / max(left[0], right[0], 1)
        clause_sim = 1.0 - abs(left[1] - right[1]) / max(left[1], right[1], 1)
        share_sim = 1.0 - abs(left[2] - right[2])
        similarities.append((length_sim + clause_sim + share_sim) / 3.0)

    return round(_safe_mean(similarities), 4)


@dataclass
class Diagnostics:
    """Full diagnostic report for one submission."""

    version: str = DIAGNOSTICS_VERSION
    wordlist_version: str = WORDLIST_VERSION
    sentence_lengths: LengthStats = field(default_factory=LengthStats)
    paragraph_lengths: LengthStats = field(default_factory=LengthStats)
    moving_average_ttr: float = 0.0
    repeated_bigram_rate: float = 0.0
    repeated_trigram_rate: float = 0.0
    repeated_fourgram_rate: float = 0.0
    repeated_sentence_openings: float = 0.0
    punctuation_per_1000_chars: dict[str, float] = field(default_factory=dict)
    function_word_frequency: dict[str, float] = field(default_factory=dict)
    transition_phrase_density: float = 0.0
    consecutive_structural_similarity: float = 0.0
    #: Populated by the pipeline from window-level scores.
    window_consistency: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_diagnostics(text: str) -> Diagnostics:
    """Compute the full diagnostic report for ``text``."""
    words = split_words(text)
    return Diagnostics(
        sentence_lengths=sentence_length_stats(text),
        paragraph_lengths=paragraph_length_stats(text),
        moving_average_ttr=moving_average_ttr(words),
        repeated_bigram_rate=repeated_ngram_rate(words, 2),
        repeated_trigram_rate=repeated_ngram_rate(words, 3),
        repeated_fourgram_rate=repeated_ngram_rate(words, 4),
        repeated_sentence_openings=repeated_sentence_openings(text),
        punctuation_per_1000_chars=punctuation_distribution(text),
        function_word_frequency=function_word_distribution(words),
        transition_phrase_density=transition_phrase_density(text),
        consecutive_structural_similarity=consecutive_structural_similarity(text),
    )
