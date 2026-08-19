"""Deterministic test double.

This backend performs no machine learning. It exists so that the API, worker,
and end-to-end tests can exercise the full analysis lifecycle without model
weights. It is explicitly named ``fake`` everywhere it appears — in settings, in
health output, and in the provenance recorded on every result — and
:func:`app.core.config.Settings` refuses to start a production process that
selects it.

The score is a stable hash of the text mapped into [0, 1]. It is meaningless as
a classification and must never be presented as one.
"""

from __future__ import annotations

import hashlib
from typing import Any

from detection.calibration import CALIBRATION_VERSION, DETECTOR_VERSION
from detection.engines.base import WindowScores
from detection.segmentation import build_windows

#: Words per pseudo-window. The fake backend has no tokenizer, so it windows on
#: whitespace tokens — still never on character offsets.
FAKE_WINDOW_TOKENS = 120
FAKE_WINDOW_STRIDE = 100


class FakeProvider:
    """Deterministic, content-independent scorer for tests and local runs."""

    backend = "fake"

    def __init__(self) -> None:
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @staticmethod
    def _stable_score(chunk: str) -> float:
        digest = hashlib.sha256(chunk.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF

    def score_text(self, text: str) -> WindowScores:
        words = text.split()
        if not words:
            return WindowScores(scores=[], token_weights=[])

        windows = build_windows(list(range(len(words))), FAKE_WINDOW_TOKENS, FAKE_WINDOW_STRIDE)
        scores: list[float] = []
        weights: list[int] = []
        for window in windows:
            chunk = " ".join(words[window.start : window.start + window.length])
            scores.append(self._stable_score(chunk))
            weights.append(window.length)
        return WindowScores(scores=scores, token_weights=weights)

    def metadata(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "is_real_model": False,
            "warning": "Deterministic test double. Output is not a classification.",
            "model_id": "fake",
            "revision": None,
            "device": "cpu",
            "calibration_version": CALIBRATION_VERSION,
            "detector_version": DETECTOR_VERSION,
        }
