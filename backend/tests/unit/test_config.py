"""Settings validation, including fail-closed production posture."""

from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.core.config import Settings

SAFE_PRODUCTION: dict[str, object] = {
    "_env_file": None,
    "environment": "production",
    "debug": False,
    "cookie_secure": True,
    "detector_backend": "modernbert",
    "secret_key": "P" * 60,
    "rate_limit_pepper": "Q" * 60,
    "encryption_key": "c2FmZS1wcm9kdWN0aW9uLWtleS0zMi1ieXRlcy1va1g=",
    "allowed_hosts": "originlens.example.com",
}


def test_development_defaults_are_usable(monkeypatch: pytest.MonkeyPatch) -> None:
    # Clear any ORIGINLENS_* variables so this asserts the built-in defaults
    # rather than whatever the surrounding environment happens to set.
    for name in list(os.environ):
        if name.startswith("ORIGINLENS_"):
            monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.is_production is False
    assert len(settings.encryption_key_bytes) == 32


class TestEncryptionKey:
    def test_non_base64_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, encryption_key="not base64 !!!")

    def test_wrong_length_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="32 bytes"):
            Settings(_env_file=None, encryption_key="c2hvcnQ=")


class TestLimits:
    def test_min_words_above_low_reliability_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, min_words=200, low_reliability_words=150)

    def test_low_reliability_above_max_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, low_reliability_words=20000, max_words=10000)

    def test_stride_above_window_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, model_max_tokens=384, model_stride=512)

    def test_negative_limits_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, max_upload_bytes=-1)


class TestProductionPosture:
    def test_safe_production_configuration_is_accepted(self) -> None:
        settings = Settings(**SAFE_PRODUCTION)  # type: ignore[arg-type]
        assert settings.is_production is True

    def test_fake_detector_is_refused_in_production(self) -> None:
        config = SAFE_PRODUCTION | {"detector_backend": "fake"}
        with pytest.raises(ValidationError, match="fake"):
            Settings(**config)  # type: ignore[arg-type]

    def test_placeholder_secret_key_is_refused(self) -> None:
        config = SAFE_PRODUCTION | {"secret_key": "dev_only_secret_key_change_me_now_ok"}
        with pytest.raises(ValidationError, match="placeholder"):
            Settings(**config)  # type: ignore[arg-type]

    def test_placeholder_encryption_key_is_refused(self) -> None:
        config = SAFE_PRODUCTION | {
            "encryption_key": "b3JpZ2lubGVucy1kZXYtb25seS1rZXktQ0hBTkdFTUU="
        }
        with pytest.raises(ValidationError, match="placeholder"):
            Settings(**config)  # type: ignore[arg-type]

    def test_short_secret_is_refused(self) -> None:
        config = SAFE_PRODUCTION | {"secret_key": "tooshort"}
        with pytest.raises(ValidationError, match="at least"):
            Settings(**config)  # type: ignore[arg-type]

    def test_debug_mode_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="DEBUG"):
            Settings(**(SAFE_PRODUCTION | {"debug": True}))  # type: ignore[arg-type]

    def test_insecure_cookies_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="COOKIE_SECURE"):
            Settings(**(SAFE_PRODUCTION | {"cookie_secure": False}))  # type: ignore[arg-type]

    def test_localhost_is_refused_as_a_production_host(self) -> None:
        config = SAFE_PRODUCTION | {"allowed_hosts": "localhost,originlens.example.com"}
        with pytest.raises(ValidationError, match="production hosts"):
            Settings(**config)  # type: ignore[arg-type]

    def test_metrics_without_a_token_are_refused(self) -> None:
        config = SAFE_PRODUCTION | {"metrics_enabled": True, "metrics_token": None}
        with pytest.raises(ValidationError, match="METRICS_TOKEN"):
            Settings(**config)  # type: ignore[arg-type]

    def test_development_tolerates_placeholders(self) -> None:
        assert Settings(_env_file=None, detector_backend="fake").detector_backend == "fake"


class TestDerivedValues:
    def test_host_and_origin_lists_are_parsed(self) -> None:
        settings = Settings(
            _env_file=None,
            allowed_hosts="a.example, b.example ",
            cors_origins="https://a.example, https://b.example",
        )
        assert settings.allowed_host_list == ["a.example", "b.example"]
        assert settings.cors_origin_list == ["https://a.example", "https://b.example"]

    def test_log_level_is_normalised(self) -> None:
        assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"

    def test_invalid_log_level_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, log_level="chatty")
