"""Score semantics, display bands, and reliability rules."""

from __future__ import annotations

import pytest

from detection.calibration import (
    CALIBRATION_VERSION,
    STABILITY_FORCE_UNCERTAIN_STDEV,
    Label,
    Reliability,
    apply_stability_override,
    assess_reliability,
    band_for,
    bands_as_dicts,
    calibrate,
)


class TestCalibration:
    def test_identity_mapping_scales_to_0_100(self) -> None:
        assert calibrate(0.0) == 0
        assert calibrate(0.5) == 50
        assert calibrate(1.0) == 100

    def test_out_of_range_values_are_clamped(self) -> None:
        assert calibrate(-3.0) == 0
        assert calibrate(9.0) == 100

    def test_calibration_version_is_declared_as_identity(self) -> None:
        # The project ships no validated calibration set; the version string
        # must say so rather than implying a fitted mapping.
        assert "identity" in CALIBRATION_VERSION


class TestBands:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0, Label.HUMAN_PATTERNED),
            (34, Label.HUMAN_PATTERNED),
            (35, Label.UNCERTAIN),
            (64, Label.UNCERTAIN),
            (65, Label.AI_PATTERNED),
            (100, Label.AI_PATTERNED),
        ],
    )
    def test_band_boundaries_are_inclusive(self, score: int, expected: Label) -> None:
        assert band_for(score) is expected

    def test_bands_cover_every_score_without_gaps(self) -> None:
        assert all(band_for(score) is not None for score in range(101))

    def test_scores_outside_range_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            band_for(101)

    def test_bands_are_serialisable_for_the_frontend(self) -> None:
        bands = bands_as_dicts()
        assert bands[0] == {"lower": 0, "upper": 34, "label": Label.HUMAN_PATTERNED.value}
        assert len(bands) == 3


class TestStabilityOverride:
    def test_confident_score_survives_when_windows_agree(self) -> None:
        assert apply_stability_override(90, 0.01) is Label.AI_PATTERNED

    def test_strong_disagreement_forces_uncertain(self) -> None:
        assert apply_stability_override(90, STABILITY_FORCE_UNCERTAIN_STDEV) is Label.UNCERTAIN
        assert apply_stability_override(5, 0.40) is Label.UNCERTAIN

    def test_uncertain_band_is_unchanged_by_override(self) -> None:
        assert apply_stability_override(50, 0.40) is Label.UNCERTAIN

    def test_missing_stability_leaves_the_band_alone(self) -> None:
        assert apply_stability_override(90, None) is Label.AI_PATTERNED


class TestReliability:
    def _assess(self, **kwargs: object):
        defaults: dict[str, object] = {
            "word_count": 400,
            "window_stability": 0.01,
            "min_words": 80,
            "low_reliability_words": 150,
            "integrity_warning_codes": [],
            "window_count": 3,
        }
        defaults.update(kwargs)
        return assess_reliability(**defaults)  # type: ignore[arg-type]

    def test_below_minimum_is_insufficient(self) -> None:
        result = self._assess(word_count=40)
        assert result.level is Reliability.INSUFFICIENT
        assert result.reasons

    def test_between_minimum_and_threshold_is_low(self) -> None:
        result = self._assess(word_count=100)
        assert result.level is Reliability.LOW
        assert any("150" in reason for reason in result.reasons)

    def test_long_stable_text_is_normal(self) -> None:
        result = self._assess(word_count=800)
        assert result.level is Reliability.NORMAL
        assert result.reasons == []

    def test_moderate_disagreement_downgrades_to_moderate(self) -> None:
        assert self._assess(window_stability=0.20).level is Reliability.MODERATE

    def test_severe_disagreement_downgrades_to_low(self) -> None:
        assert self._assess(window_stability=0.40).level is Reliability.LOW

    def test_single_window_disagreement_is_ignored(self) -> None:
        assert self._assess(window_stability=0.9, window_count=1).level is Reliability.NORMAL

    def test_homoglyph_warning_downgrades_reliability(self) -> None:
        result = self._assess(integrity_warning_codes=["homoglyph_risk"])
        assert result.level is Reliability.LOW
        assert any("script" in reason for reason in result.reasons)

    def test_reasons_are_returned_instead_of_a_confidence_percentage(self) -> None:
        result = self._assess(word_count=100)
        assert isinstance(result.reasons, list)
        assert not hasattr(result, "confidence")
