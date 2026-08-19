"""Token-weighted aggregation of per-window model scores."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Aggregate:
    """Aggregated model output across windows."""

    raw_score: float
    #: Population standard deviation of window scores; 0.0 for a single window.
    stability: float
    window_count: int
    window_scores: list[float]

    @property
    def consistency(self) -> float:
        """Convenience inverse of ``stability``, clamped to [0, 1]."""
        return round(max(0.0, 1.0 - self.stability * 2.0), 4)


def aggregate_windows(scores: Sequence[float], token_weights: Sequence[int]) -> Aggregate:
    """Combine per-window scores, weighting each window by its token count.

    Token weighting prevents a short trailing window from carrying the same
    influence as a full-length one.
    """
    if len(scores) != len(token_weights):
        raise ValueError("scores and token_weights must be the same length")
    if not scores:
        raise ValueError("at least one window score is required")

    total_weight = sum(token_weights)
    if total_weight <= 0:
        raise ValueError("token weights must sum to a positive value")

    weighted = sum(s * w for s, w in zip(scores, token_weights, strict=True))
    raw = weighted / total_weight

    stability = float(statistics.pstdev(scores)) if len(scores) > 1 else 0.0

    return Aggregate(
        raw_score=round(min(max(raw, 0.0), 1.0), 6),
        stability=round(stability, 6),
        window_count=len(scores),
        window_scores=[round(float(s), 6) for s in scores],
    )
