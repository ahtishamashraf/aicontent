"""Transformer sequence-classification provider.

Design constraints from the specification:

* Model ID and revision are configuration, never hard-coded.
* The AI-bearing class is resolved from ``id2label`` / ``label2id`` semantics.
  Index order is *not* assumed — a checkpoint whose labels cannot be interpreted
  is rejected at load time rather than scored against a guess.
* Weights load once per process and are reused.
* CPU by default; CUDA only when configured and actually available.
* Every result records model id, revision or resolved commit, Transformers and
  PyTorch versions, device, calibration version, and detector version.
* Failures raise bounded, content-free errors. There is no fallback to the fake
  backend — a broken model surfaces as an error, never as a fabricated score.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from detection.calibration import CALIBRATION_VERSION, DETECTOR_VERSION
from detection.engines.base import (
    LabelMappingError,
    ModelInferenceError,
    ModelLoadError,
    WindowScores,
)
from detection.segmentation import build_windows

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

#: Label names that denote machine-generated text.
AI_LABEL_TOKENS = ("ai", "machine", "generated", "fake", "gpt", "llm", "synthetic", "bot")

#: Label names that denote human-written text.
HUMAN_LABEL_TOKENS = ("human", "real", "genuine", "authentic", "original", "person")

#: Generic labels that carry no semantics and must not be guessed at.
UNINFORMATIVE_LABELS = ("label_0", "label_1", "0", "1", "class_0", "class_1")


class ModernBertProvider:
    """Sequence-classification provider for a locally hosted checkpoint."""

    backend = "modernbert"

    def __init__(
        self,
        model_id: str,
        *,
        revision: str | None = None,
        device: str = "auto",
        max_tokens: int = 384,
        stride: int = 320,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.requested_device = device
        self.max_tokens = max_tokens
        self.stride = stride

        self._tokenizer: Any = None
        self._model: Any = None
        self._device: str = "cpu"
        self._ai_index: int | None = None
        self._label_names: dict[int, str] = {}
        self._resolved_commit: str | None = None
        self._torch_version: str | None = None
        self._transformers_version: str | None = None
        self._lock = threading.Lock()

    # -- loading ------------------------------------------------------------
    @property
    def is_loaded(self) -> bool:
        return self._model is not None and self._ai_index is not None

    def _resolve_device(self, torch_module: Any) -> str:
        if self.requested_device == "cpu":
            return "cpu"
        cuda_available = bool(torch_module.cuda.is_available())
        if self.requested_device == "cuda":
            if not cuda_available:
                raise ModelLoadError(
                    "CUDA was requested but no CUDA device is available",
                    code="cuda_unavailable",
                )
            return "cuda"
        return "cuda" if cuda_available else "cpu"

    def load(self) -> None:
        """Load tokenizer and weights once, then validate label semantics."""
        with self._lock:
            if self.is_loaded:
                return
            try:
                import torch
                import transformers
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
            except ImportError as exc:
                raise ModelLoadError(
                    "PyTorch and Transformers are required for the real detector; "
                    "install the 'ml' extra",
                    code="ml_dependencies_missing",
                ) from exc

            self._torch_version = str(torch.__version__)
            self._transformers_version = str(transformers.__version__)

            try:
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self.model_id, revision=self.revision
                )
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_id,
                    revision=self.revision,
                    # Refuse pickle-based checkpoints: loading one executes code.
                    use_safetensors=True,
                )
            except Exception as exc:
                raise ModelLoadError(
                    f"Could not load model '{self.model_id}': {type(exc).__name__}",
                    code="model_load_failed",
                ) from exc

            self._device = self._resolve_device(torch)
            self._model.to(self._device)
            self._model.eval()

            self._ai_index = self._resolve_ai_index(self._model.config)
            self._resolved_commit = self._read_commit_hash()

    def _read_commit_hash(self) -> str | None:
        """Best-effort resolved commit for provenance."""
        for holder in (self._model, self._tokenizer):
            commit = getattr(holder, "_commit_hash", None) or getattr(
                getattr(holder, "config", None), "_commit_hash", None
            )
            if isinstance(commit, str) and commit:
                return commit
        return None

    def _resolve_ai_index(self, config: Any) -> int:
        """Determine which output index means 'AI-generated'.

        Raises when the mapping is absent, generic, or contradictory. Guessing
        an index would invert every prediction on half of all checkpoints.
        """
        id2label = getattr(config, "id2label", None)
        if not isinstance(id2label, dict) or not id2label:
            raise LabelMappingError(
                "Model config has no id2label mapping, so the AI class cannot be " "identified"
            )

        labels = {int(idx): str(name).strip().lower() for idx, name in id2label.items()}
        self._label_names = labels

        num_labels = int(getattr(config, "num_labels", len(labels)))
        if num_labels != 2 or len(labels) != 2:
            raise LabelMappingError(f"Expected a binary classifier, found {num_labels} labels")

        if all(name in UNINFORMATIVE_LABELS for name in labels.values()):
            raise LabelMappingError(
                "Model labels are generic placeholders (LABEL_0/LABEL_1); the AI "
                "class cannot be determined without an explicit mapping"
            )

        ai_matches = [i for i, name in labels.items() if self._matches(name, AI_LABEL_TOKENS)]
        human_matches = [i for i, name in labels.items() if self._matches(name, HUMAN_LABEL_TOKENS)]

        # Cross-check against label2id when present: a disagreement means the
        # config is internally inconsistent and must not be trusted.
        label2id = getattr(config, "label2id", None)
        if isinstance(label2id, dict) and label2id:
            for name, idx in label2id.items():
                expected = labels.get(int(idx))
                if expected is not None and str(name).strip().lower() != expected:
                    raise LabelMappingError(
                        "id2label and label2id disagree; the checkpoint's label "
                        "mapping is inconsistent"
                    )

        if len(ai_matches) == 1 and len(human_matches) <= 1:
            if human_matches and human_matches[0] == ai_matches[0]:
                raise LabelMappingError("A single label matched both AI and human terms")
            return ai_matches[0]

        # Exactly one human label and no AI label: the other index is the AI class.
        if len(human_matches) == 1 and not ai_matches:
            return next(i for i in labels if i != human_matches[0])

        if len(ai_matches) > 1:
            raise LabelMappingError("Multiple labels matched AI terms; mapping is ambiguous")

        raise LabelMappingError(
            f"Could not identify the AI class from labels {sorted(labels.values())}"
        )

    @staticmethod
    def _matches(label: str, tokens: tuple[str, ...]) -> bool:
        parts = {p for p in label.replace("-", "_").replace(" ", "_").split("_") if p}
        return any(token in parts for token in tokens) or any(label == token for token in tokens)

    # -- inference ----------------------------------------------------------
    def score_text(self, text: str) -> WindowScores:
        """Score ``text`` in overlapping token windows."""
        if not self.is_loaded:
            raise ModelInferenceError(
                "Provider used before load() completed", code="model_not_loaded"
            )

        import torch

        try:
            token_ids: list[int] = self._tokenizer(
                text, add_special_tokens=False, truncation=False
            )["input_ids"]
        except Exception as exc:
            raise ModelInferenceError(
                f"Tokenization failed: {type(exc).__name__}", code="tokenization_failed"
            ) from exc

        if not token_ids:
            return WindowScores(scores=[], token_weights=[])

        # Reserve room for the special tokens the tokenizer adds back.
        special = int(self._tokenizer.num_special_tokens_to_add(pair=False))
        content_budget = max(1, self.max_tokens - special)
        stride = min(self.stride, content_budget)

        windows = build_windows(token_ids, content_budget, stride)
        scores: list[float] = []
        weights: list[int] = []

        assert self._ai_index is not None
        for window in windows:
            try:
                encoded = self._tokenizer.prepare_for_model(
                    list(window.token_ids), return_tensors="pt"
                ).to(self._device)
                with torch.inference_mode():
                    logits = self._model(**encoded).logits
                probabilities = torch.softmax(logits.float(), dim=-1)
                value = float(probabilities[0, self._ai_index].item())
            except Exception as exc:
                raise ModelInferenceError(
                    f"Inference failed: {type(exc).__name__}", code="model_inference_failed"
                ) from exc

            if not (value == value) or value in (float("inf"), float("-inf")):
                raise ModelInferenceError(
                    "Model produced a non-finite score", code="model_output_not_finite"
                )

            scores.append(value)
            weights.append(window.length)

        return WindowScores(scores=scores, token_weights=weights)

    # -- provenance ---------------------------------------------------------
    def metadata(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "is_real_model": True,
            "model_id": self.model_id,
            "revision": self.revision,
            "resolved_commit": self._resolved_commit,
            "device": self._device,
            "torch_version": self._torch_version,
            "transformers_version": self._transformers_version,
            "max_tokens": self.max_tokens,
            "stride": self.stride,
            "label_names": self._label_names or None,
            "ai_label_index": self._ai_index,
            "calibration_version": CALIBRATION_VERSION,
            "detector_version": DETECTOR_VERSION,
        }
