"""Detector provider contracts, including strict label-mapping validation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from detection.engines.base import (
    DetectorProvider,
    LabelMappingError,
    ModelInferenceError,
    WindowScores,
)
from detection.engines.fake import FakeProvider
from detection.engines.modernbert import ModernBertProvider
from detection.registry import build_provider, reset_provider


class TestFakeProvider:
    def test_satisfies_the_provider_protocol(self, provider: FakeProvider) -> None:
        assert isinstance(provider, DetectorProvider)

    def test_output_is_deterministic(self, provider: FakeProvider) -> None:
        text = " ".join(f"word{i}" for i in range(300))
        assert provider.score_text(text).scores == provider.score_text(text).scores

    def test_scores_are_within_the_unit_range(self, provider: FakeProvider) -> None:
        text = " ".join(f"word{i}" for i in range(500))
        assert all(0.0 <= s <= 1.0 for s in provider.score_text(text).scores)

    def test_weights_match_window_lengths(self, provider: FakeProvider) -> None:
        result = provider.score_text(" ".join(f"w{i}" for i in range(500)))
        assert len(result.scores) == len(result.token_weights)
        assert all(w > 0 for w in result.token_weights)

    def test_empty_text_produces_no_windows(self, provider: FakeProvider) -> None:
        assert provider.score_text("   ").scores == []

    def test_metadata_declares_itself_as_not_a_real_model(self, provider: FakeProvider) -> None:
        metadata = provider.metadata()
        assert metadata["is_real_model"] is False
        assert metadata["backend"] == "fake"
        assert "not a classification" in metadata["warning"]


class TestWindowScores:
    def test_mismatched_lengths_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            WindowScores(scores=[0.1, 0.2], token_weights=[10])


def _config(
    id2label: dict[int, str], label2id: dict[str, int] | None = None, num_labels: int | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id2label=id2label,
        label2id=label2id if label2id is not None else {v: k for k, v in id2label.items()},
        num_labels=num_labels if num_labels is not None else len(id2label),
    )


class TestLabelMapping:
    """Index order must never be assumed: guessing inverts half of all models."""

    @pytest.fixture
    def provider(self) -> ModernBertProvider:
        return ModernBertProvider("test/model")

    @pytest.mark.parametrize(
        ("labels", "expected"),
        [
            ({0: "human", 1: "ai"}, 1),
            ({0: "ai", 1: "human"}, 0),
            ({0: "Human", 1: "AI"}, 1),
            ({0: "machine-generated", 1: "human-written"}, 0),
            ({0: "Real", 1: "Fake"}, 1),
            ({0: "human", 1: "something_else"}, 1),
        ],
    )
    def test_ai_index_is_resolved_from_label_semantics(
        self, provider: ModernBertProvider, labels: dict[int, str], expected: int
    ) -> None:
        assert provider._resolve_ai_index(_config(labels)) == expected

    @pytest.mark.parametrize(
        "labels",
        [
            {0: "LABEL_0", 1: "LABEL_1"},
            {0: "positive", 1: "negative"},
            {0: "ai", 1: "gpt"},
            {0: "human", 1: "ai", 2: "mixed"},
        ],
    )
    def test_ambiguous_or_generic_mappings_are_rejected(
        self, provider: ModernBertProvider, labels: dict[int, str]
    ) -> None:
        with pytest.raises(LabelMappingError):
            provider._resolve_ai_index(_config(labels))

    def test_missing_mapping_is_rejected(self, provider: ModernBertProvider) -> None:
        with pytest.raises(LabelMappingError):
            provider._resolve_ai_index(SimpleNamespace(id2label=None, label2id=None, num_labels=2))

    def test_contradictory_id2label_and_label2id_are_rejected(
        self, provider: ModernBertProvider
    ) -> None:
        with pytest.raises(LabelMappingError):
            provider._resolve_ai_index(
                _config({0: "human", 1: "ai"}, label2id={"human": 1, "ai": 0})
            )

    def test_scoring_before_load_raises_rather_than_guessing(
        self, provider: ModernBertProvider
    ) -> None:
        with pytest.raises(ModelInferenceError):
            provider.score_text("some text")

    def test_metadata_records_full_provenance_fields(self, provider: ModernBertProvider) -> None:
        metadata = provider.metadata()
        for field in (
            "model_id",
            "revision",
            "resolved_commit",
            "device",
            "torch_version",
            "transformers_version",
            "calibration_version",
            "detector_version",
        ):
            assert field in metadata
        assert metadata["is_real_model"] is True


class TestRegistry:
    def teardown_method(self) -> None:
        reset_provider()

    def test_development_builds_the_fake_backend(self) -> None:
        settings = Settings(_env_file=None, detector_backend="fake")
        assert isinstance(build_provider(settings), FakeProvider)

    def test_modernbert_backend_is_constructed_with_configured_values(self) -> None:
        settings = Settings(
            _env_file=None,
            detector_backend="modernbert",
            model_id="some/model",
            model_revision="abc123",
            model_max_tokens=512,
            model_stride=400,
        )
        built = build_provider(settings)
        assert isinstance(built, ModernBertProvider)
        assert built.model_id == "some/model"
        assert built.revision == "abc123"
        assert built.max_tokens == 512
        assert built.stride == 400
