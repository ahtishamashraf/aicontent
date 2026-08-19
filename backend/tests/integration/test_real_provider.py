"""Exercise the real transformer provider against a locally-built checkpoint.

Downloading a published detector is blocked by network policy in some
environments, and a published checkpoint is not needed to prove the provider
works: a tiny, randomly-initialised sequence-classification model built on disk
exercises the same load path, label resolution, tokenizer windowing, and
inference code.

The scores such a model returns are meaningless, so nothing here asserts a
classification. What is asserted is that inference runs, output is finite and
in range, windows are token-weighted, and provenance is recorded.

``make model-smoke`` remains the separate command that exercises the *configured*
production model.
"""

from __future__ import annotations

import pathlib

import pytest

torch = pytest.importorskip("torch", reason="PyTorch is not installed")
transformers = pytest.importorskip("transformers", reason="Transformers is not installed")

from detection.aggregation import aggregate_windows  # noqa: E402
from detection.calibration import calibrate  # noqa: E402
from detection.engines.base import LabelMappingError, ModelLoadError  # noqa: E402
from detection.engines.modernbert import ModernBertProvider  # noqa: E402

pytestmark = pytest.mark.model

VOCAB = (
    ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"]
    + [chr(c) for c in range(97, 123)]
    + [
        "the",
        "committee",
        "reviewed",
        "proposal",
        "timeline",
        "staffing",
        "chair",
        "archive",
        "migration",
        "recruitment",
        "session",
        "members",
        "concerns",
        "delivery",
        "schedule",
        "meeting",
        "department",
        "vacancies",
        "workload",
        "candidates",
        ".",
        ",",
        "and",
        "a",
        "of",
        "to",
        "in",
        "that",
        "was",
    ]
)

SAMPLE = (
    "the committee reviewed the proposal and members raised concerns about the "
    "delivery timeline in that session . the chair reviewed a schedule of the "
    "meeting and the department reviewed staffing vacancies and workload . "
) * 4


def _build_checkpoint(
    directory: pathlib.Path,
    id2label: dict[int, str],
    label2id: dict[str, int] | None = None,
) -> str:
    """Write a real (tiny) safetensors checkpoint and tokenizer to ``directory``."""
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "vocab.txt").write_text("\n".join(VOCAB) + "\n")

    tokenizer = BertTokenizerFast(vocab_file=str(directory / "vocab.txt"), do_lower_case=True)
    tokenizer.save_pretrained(directory)

    config = BertConfig(
        vocab_size=len(VOCAB),
        hidden_size=32,
        num_hidden_layers=2,
        num_attention_heads=2,
        intermediate_size=64,
        max_position_embeddings=512,
        num_labels=len(id2label),
        id2label=id2label,
        label2id=label2id or {v: k for k, v in id2label.items()},
    )
    BertForSequenceClassification(config).save_pretrained(directory, safe_serialization=True)
    return str(directory)


@pytest.fixture(scope="module")
def checkpoint(tmp_path_factory: pytest.TempPathFactory) -> str:
    return _build_checkpoint(tmp_path_factory.mktemp("detector"), {0: "human", 1: "ai"})


@pytest.fixture(scope="module")
def provider(checkpoint: str) -> ModernBertProvider:
    instance = ModernBertProvider(checkpoint, device="cpu", max_tokens=64, stride=48)
    instance.load()
    return instance


class TestLoading:
    def test_checkpoint_loads(self, provider: ModernBertProvider) -> None:
        assert provider.is_loaded is True

    def test_load_is_idempotent(self, provider: ModernBertProvider) -> None:
        provider.load()
        assert provider.is_loaded is True

    def test_ai_label_index_is_resolved_from_the_config(self, provider: ModernBertProvider) -> None:
        assert provider.metadata()["ai_label_index"] == 1
        assert provider.metadata()["label_names"] == {0: "human", 1: "ai"}

    def test_reversed_labels_resolve_to_the_other_index(self, tmp_path: pathlib.Path) -> None:
        # The same weights with swapped labels must flip which index is read.
        path = _build_checkpoint(tmp_path / "reversed", {0: "ai", 1: "human"})
        instance = ModernBertProvider(path, device="cpu", max_tokens=64, stride=48)
        instance.load()
        assert instance.metadata()["ai_label_index"] == 0

    def test_generic_labels_are_refused_at_load_time(self, tmp_path: pathlib.Path) -> None:
        path = _build_checkpoint(tmp_path / "generic", {0: "LABEL_0", 1: "LABEL_1"})
        instance = ModernBertProvider(path, device="cpu")
        with pytest.raises(LabelMappingError):
            instance.load()

    def test_missing_checkpoint_raises_a_bounded_error(self) -> None:
        instance = ModernBertProvider("/nonexistent/model/path", device="cpu")
        with pytest.raises(ModelLoadError) as excinfo:
            instance.load()
        assert excinfo.value.code == "model_load_failed"
        assert len(excinfo.value.detail) <= 300

    def test_cuda_request_without_a_device_is_refused_not_downgraded(self, checkpoint: str) -> None:
        if torch.cuda.is_available():
            pytest.skip("CUDA is present, so this refusal cannot be observed")
        instance = ModernBertProvider(checkpoint, device="cuda")
        with pytest.raises(ModelLoadError) as excinfo:
            instance.load()
        assert excinfo.value.code == "cuda_unavailable"


class TestInference:
    def test_inference_produces_one_score_per_window(self, provider: ModernBertProvider) -> None:
        result = provider.score_text(SAMPLE)
        assert len(result.scores) >= 2
        assert len(result.scores) == len(result.token_weights)

    def test_every_score_is_finite_and_in_range(self, provider: ModernBertProvider) -> None:
        for score in provider.score_text(SAMPLE).scores:
            assert score == score, "NaN"
            assert score not in (float("inf"), float("-inf"))
            assert 0.0 <= score <= 1.0

    def test_no_window_exceeds_the_configured_token_budget(
        self, provider: ModernBertProvider
    ) -> None:
        assert all(weight <= 64 for weight in provider.score_text(SAMPLE).token_weights)

    def test_inference_is_deterministic_in_eval_mode(self, provider: ModernBertProvider) -> None:
        assert provider.score_text(SAMPLE).scores == provider.score_text(SAMPLE).scores

    def test_empty_text_produces_no_windows(self, provider: ModernBertProvider) -> None:
        assert provider.score_text("").scores == []

    def test_aggregate_and_calibrated_score_are_well_formed(
        self, provider: ModernBertProvider
    ) -> None:
        result = provider.score_text(SAMPLE)
        aggregate = aggregate_windows(result.scores, result.token_weights)
        assert 0.0 <= aggregate.raw_score <= 1.0
        assert 0 <= calibrate(aggregate.raw_score) <= 100

    def test_long_input_is_windowed_rather_than_truncated(
        self, provider: ModernBertProvider
    ) -> None:
        short = provider.score_text(SAMPLE)
        long = provider.score_text(SAMPLE * 4)
        assert len(long.scores) > len(short.scores)
        assert sum(long.token_weights) > sum(short.token_weights)


class TestProvenance:
    def test_metadata_records_real_versions_and_device(self, provider: ModernBertProvider) -> None:
        metadata = provider.metadata()
        assert metadata["is_real_model"] is True
        assert metadata["torch_version"] == torch.__version__
        assert metadata["transformers_version"] == transformers.__version__
        assert metadata["device"] in {"cpu", "cuda"}
        assert metadata["calibration_version"]
        assert metadata["detector_version"]

    def test_metadata_carries_no_submitted_text(self, provider: ModernBertProvider) -> None:
        provider.score_text(SAMPLE)
        assert "committee" not in str(provider.metadata())
