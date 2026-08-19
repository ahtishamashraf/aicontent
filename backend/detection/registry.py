"""Process-wide detector provider registry.

The provider is constructed once per process and reused. A load failure is
recorded and re-raised: the fake backend is **never** substituted for a real one
that failed, because a fabricated score is worse than an honest error.
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.config import Settings, get_settings
from detection.engines.base import DetectorProvider, ModelLoadError
from detection.engines.fake import FakeProvider
from detection.engines.modernbert import ModernBertProvider

_provider: DetectorProvider | None = None
_load_error: ModelLoadError | None = None
_lock = threading.Lock()


def build_provider(settings: Settings) -> DetectorProvider:
    """Construct (but do not load) the configured provider."""
    if settings.detector_backend == "fake":
        if settings.is_production:
            # Belt and braces: settings validation already refuses this.
            raise ModelLoadError(
                "The fake detector cannot be used in production",
                code="fake_detector_in_production",
            )
        return FakeProvider()
    if settings.detector_backend == "modernbert":
        return ModernBertProvider(
            settings.model_id,
            revision=settings.model_revision or None,
            device=settings.model_device,
            max_tokens=settings.model_max_tokens,
            stride=settings.model_stride,
        )
    raise ModelLoadError(
        f"Unknown detector backend '{settings.detector_backend}'",
        code="unknown_backend",
    )


def get_provider(settings: Settings | None = None) -> DetectorProvider:
    """Return the loaded process-wide provider, loading it on first use."""
    global _provider, _load_error

    if _load_error is not None:
        raise _load_error

    if _provider is not None and _provider.is_loaded:
        return _provider

    with _lock:
        if _load_error is not None:
            raise _load_error
        if _provider is not None and _provider.is_loaded:
            return _provider

        settings = settings or get_settings()
        provider = build_provider(settings)
        try:
            provider.load()
        except ModelLoadError as exc:
            _load_error = exc
            raise
        except Exception as exc:
            _load_error = ModelLoadError(f"Provider failed to load: {type(exc).__name__}")
            raise _load_error from exc

        _provider = provider
        return provider


def provider_status(settings: Settings | None = None) -> dict[str, Any]:
    """Readiness snapshot for the health endpoints. Never raises."""
    settings = settings or get_settings()
    status: dict[str, Any] = {
        "backend": settings.detector_backend,
        "is_real_model": settings.detector_backend != "fake",
        "loaded": bool(_provider is not None and _provider.is_loaded),
    }
    if _load_error is not None:
        status["load_error_code"] = _load_error.code
        status["load_error_detail"] = _load_error.detail
    if _provider is not None and _provider.is_loaded:
        status["model"] = _provider.metadata()
    return status


def reset_provider() -> None:
    """Clear the cached provider. Used by tests and worker fork hooks."""
    global _provider, _load_error
    _provider = None
    _load_error = None
