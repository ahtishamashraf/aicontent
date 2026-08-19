"""Detector provider protocol and shared result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class DetectorError(RuntimeError):
    """Base class for provider failures.

    ``code`` is a short, stable identifier safe to return to a client.
    ``detail`` is bounded and must never contain submitted text.
    """

    code = "detector_error"

    def __init__(self, detail: str = "", *, code: str | None = None):
        super().__init__(detail or self.code)
        if code:
            self.code = code
        #: Bounded so a library exception cannot smuggle content into a response.
        self.detail = detail[:300]


class ModelLoadError(DetectorError):
    code = "model_load_failed"


class ModelInferenceError(DetectorError):
    code = "model_inference_failed"


class LabelMappingError(ModelLoadError):
    code = "model_label_mapping_invalid"


@dataclass
class WindowScores:
    """Per-window model output and the token weight of each window."""

    scores: list[float] = field(default_factory=list)
    token_weights: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.scores) != len(self.token_weights):
            raise ValueError("scores and token_weights must be the same length")


@runtime_checkable
class DetectorProvider(Protocol):
    """A scoring backend.

    Implementations must be safe to load once per process and then reuse.
    """

    #: Stable identifier for the backend, e.g. "fake" or "modernbert".
    backend: str

    def load(self) -> None:
        """Load weights and validate configuration. Idempotent."""

    @property
    def is_loaded(self) -> bool:
        """Whether the provider is ready to serve inference."""
        ...

    def score_text(self, text: str) -> WindowScores:
        """Score ``text``, returning one value in [0, 1] per model window."""
        ...

    def metadata(self) -> dict[str, Any]:
        """Provenance recorded with every result. Never contains content."""
        ...
