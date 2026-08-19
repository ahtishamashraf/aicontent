"""Application settings with fail-closed production validation.

Every value is sourced from the environment with the ``ORIGINLENS_`` prefix.
Production deployments are rejected at import time when secrets are missing,
left at their development defaults, or when the fake detector is selected.
"""

from __future__ import annotations

import base64
import functools
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
DetectorBackend = Literal["fake", "modernbert"]
ModelDevice = Literal["auto", "cpu", "cuda"]

#: Placeholder markers that must never survive into a production deployment.
_PLACEHOLDER_MARKERS = ("change_me", "changeme", "dev_only", "placeholder", "insecure")

#: Minimum acceptable length for high-entropy secrets.
_MIN_SECRET_LENGTH = 32


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    """Validated runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ORIGINLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- Runtime -------------------------------------------------------------
    environment: Environment = "development"
    debug: bool = False
    log_level: str = "INFO"

    # --- Infrastructure ------------------------------------------------------
    database_url: str = "postgresql+psycopg://originlens:originlens@localhost:5432/originlens"
    redis_url: str = "redis://localhost:6379/0"

    # --- Secrets -------------------------------------------------------------
    # Development default only; _validate_production_posture refuses it in production.
    secret_key: str = "dev_only_secret_key_not_for_production_use_change_me"  # noqa: S105
    encryption_key: str = "b3JpZ2lubGVucy1kZXYtb25seS1rZXktQ0hBTkdFTUU="
    rate_limit_pepper: str = "dev_only_rate_limit_pepper_change_me"

    # --- Detector ------------------------------------------------------------
    detector_backend: DetectorBackend = "fake"
    model_id: str = "answerdotai/ModernBERT-base"
    model_revision: str | None = None
    model_device: ModelDevice = "auto"
    model_max_tokens: Annotated[int, Field(ge=64, le=8192)] = 384
    model_stride: Annotated[int, Field(ge=32, le=8192)] = 320
    hf_home: str | None = None

    # --- Input limits --------------------------------------------------------
    min_words: Annotated[int, Field(ge=1, le=10_000)] = 80
    low_reliability_words: Annotated[int, Field(ge=1, le=100_000)] = 150
    max_words: Annotated[int, Field(ge=100, le=1_000_000)] = 10_000
    max_characters: Annotated[int, Field(ge=500, le=5_000_000)] = 50_000
    max_upload_bytes: Annotated[int, Field(ge=1024, le=104_857_600)] = 5_242_880
    english_confidence_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.60

    # --- Sessions ------------------------------------------------------------
    session_ttl_seconds: Annotated[int, Field(ge=300, le=31_536_000)] = 1_209_600
    session_idle_timeout_seconds: Annotated[int, Field(ge=300, le=31_536_000)] = 604_800
    cookie_secure: bool = True
    cookie_domain: str | None = None

    # --- Retention -----------------------------------------------------------
    guest_retention_hours: Annotated[int, Field(ge=1, le=8760)] = 24
    analysis_retention_days: Annotated[int, Field(ge=1, le=3650)] = 365

    # --- Network -------------------------------------------------------------
    allowed_hosts: str = "localhost,127.0.0.1"
    cors_origins: str = "http://localhost:3000"

    # --- Email ---------------------------------------------------------------
    smtp_host: str = "localhost"
    smtp_port: Annotated[int, Field(ge=1, le=65535)] = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = False
    email_from: str = "no-reply@originlens.local"

    # --- Observability -------------------------------------------------------
    metrics_enabled: bool = False
    metrics_token: str | None = None

    # --- Derived helpers -----------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def encryption_key_bytes(self) -> bytes:
        """Decoded 32-byte AES-GCM key."""
        return base64.urlsafe_b64decode(self.encryption_key)

    # --- Validators ----------------------------------------------------------
    @field_validator("encryption_key")
    @classmethod
    def _validate_encryption_key(cls, value: str) -> str:
        try:
            raw = base64.urlsafe_b64decode(value)
        except Exception as exc:
            raise ValueError(
                "ORIGINLENS_ENCRYPTION_KEY must be urlsafe base64 of 32 random bytes"
            ) from exc
        if len(raw) != 32:
            raise ValueError(
                f"ORIGINLENS_ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(raw)}"
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper

    @model_validator(mode="after")
    def _validate_limits(self) -> Settings:
        if self.min_words > self.low_reliability_words:
            raise ValueError("min_words must not exceed low_reliability_words")
        if self.low_reliability_words > self.max_words:
            raise ValueError("low_reliability_words must not exceed max_words")
        if self.model_stride > self.model_max_tokens:
            raise ValueError("model_stride must not exceed model_max_tokens")
        return self

    @model_validator(mode="after")
    def _validate_production_posture(self) -> Settings:
        """Fail closed: refuse to start production with unsafe configuration."""
        if not self.is_production:
            return self

        problems: list[str] = []

        if self.detector_backend == "fake":
            problems.append(
                "ORIGINLENS_DETECTOR_BACKEND=fake is a test double and is refused in production"
            )
        if self.debug:
            problems.append("ORIGINLENS_DEBUG must be false in production")
        if not self.cookie_secure:
            problems.append("ORIGINLENS_COOKIE_SECURE must be true in production")

        for name, value in (
            ("ORIGINLENS_SECRET_KEY", self.secret_key),
            ("ORIGINLENS_RATE_LIMIT_PEPPER", self.rate_limit_pepper),
        ):
            if _looks_like_placeholder(value):
                problems.append(f"{name} still contains a development placeholder value")
            elif len(value) < _MIN_SECRET_LENGTH:
                problems.append(f"{name} must be at least {_MIN_SECRET_LENGTH} characters")

        # The encryption key is base64-encoded, so markers live in the decoded bytes.
        decoded_key = self.encryption_key_bytes.decode("utf-8", errors="ignore")
        if _looks_like_placeholder(self.encryption_key) or _looks_like_placeholder(decoded_key):
            problems.append(
                "ORIGINLENS_ENCRYPTION_KEY still contains a development placeholder value"
            )

        if self.metrics_enabled and not self.metrics_token:
            problems.append(
                "ORIGINLENS_METRICS_TOKEN is required when metrics are enabled in production"
            )
        if "localhost" in self.allowed_host_list or not self.allowed_host_list:
            problems.append("ORIGINLENS_ALLOWED_HOSTS must name real production hosts")

        if problems:
            raise ValueError(
                "Refusing to start with unsafe production configuration:\n  - "
                + "\n  - ".join(problems)
            )
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
