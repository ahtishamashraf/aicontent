"""Weighted aggregation and stability."""

from __future__ import annotations

import pytest

from detection.aggregation import aggregate_windows


def test_single_window_returns_its_own_score_and_zero_stability() -> None:
    result = aggregate_windows([0.73], [384])
    assert result.raw_score == pytest.approx(0.73)
    assert result.stability == 0.0
    assert result.window_count == 1


def test_aggregation_is_weighted_by_token_count() -> None:
    # A short window must not carry the same influence as a full one.
    weighted = aggregate_windows([1.0, 0.0], [900, 100]).raw_score
    assert weighted == pytest.approx(0.9)
    assert weighted != pytest.approx(0.5), "must not be a plain mean"


def test_equal_weights_reduce_to_the_mean() -> None:
    assert aggregate_windows([0.2, 0.4, 0.6], [100, 100, 100]).raw_score == pytest.approx(0.4)


def test_stability_is_zero_when_windows_agree() -> None:
    assert aggregate_windows([0.5, 0.5, 0.5], [100, 100, 100]).stability == 0.0


def test_stability_grows_with_disagreement() -> None:
    agree = aggregate_windows([0.50, 0.52, 0.49], [100, 100, 100]).stability
    disagree = aggregate_windows([0.05, 0.95, 0.50], [100, 100, 100]).stability
    assert disagree > agree


def test_consistency_is_the_inverse_of_stability() -> None:
    assert aggregate_windows([0.5, 0.5], [10, 10]).consistency == 1.0
    assert aggregate_windows([0.0, 1.0], [10, 10]).consistency < 0.2


def test_result_is_clamped_to_unit_range() -> None:
    assert 0.0 <= aggregate_windows([1.5, -0.5], [10, 10]).raw_score <= 1.0


def test_mismatched_inputs_are_rejected() -> None:
    with pytest.raises(ValueError):
        aggregate_windows([0.5, 0.5], [100])


def test_empty_input_is_rejected() -> None:
    with pytest.raises(ValueError):
        aggregate_windows([], [])


def test_zero_total_weight_is_rejected() -> None:
    with pytest.raises(ValueError):
        aggregate_windows([0.5], [0])
