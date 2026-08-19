"""Request and response schemas.

Response models are explicit so that no ORM field can leak into a payload by
accident — in particular ``encrypted_text``, ``password_hash``, and token
digests have no schema representation at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

#: Password policy. Length is the control that matters; composition rules push
#: users toward predictable substitutions without adding real entropy.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


class ErrorDetail(BaseModel):
    code: str
    message: str
    correlation_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def _reject_trivial(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password must not begin or end with whitespace")
        if len(set(value)) < 5:
            raise ValueError("Password is too repetitive")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    status: str
    email_verified_at: datetime | None
    created_at: datetime


class SessionResponse(BaseModel):
    """Answer to "who am I".

    ``user`` is null for an anonymous caller. This deliberately returns 200
    rather than 401: not being signed in is a valid answer to the question, and
    a 401 on every page load fills the browser console with errors that then
    hide real ones.
    """

    user: UserProfile | None = None


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
class AnalyzeTextRequest(BaseModel):
    text: str = Field(min_length=1)
    store_original_text: bool = False


class SegmentResponse(BaseModel):
    id: str
    index: int
    text: str | None = None
    word_count: int
    character_count: int
    public_score: int | None = None
    raw_model_score: float | None = None
    label: str | None = None
    too_short: bool = False
    grouped_with_context: bool = False


class IntegrityWarningResponse(BaseModel):
    code: str
    message: str


class CountsResponse(BaseModel):
    words: int
    characters: int
    paragraphs: int


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    status: str
    source: str
    source_filename: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    label: str | None = None
    public_score: int | None = None
    raw_model_score: float | None = None
    reliability: str | None = None
    reliability_reasons: list[str] = Field(default_factory=list)

    counts: CountsResponse
    detected_language: str | None = None
    language_confidence: float | None = None
    window_stability: float | None = None

    segments: list[SegmentResponse] = Field(default_factory=list)
    integrity_warnings: list[IntegrityWarningResponse] = Field(default_factory=list)
    diagnostics: dict[str, Any] | None = None

    model_metadata: dict[str, Any] | None = None
    calibration_version: str | None = None
    detector_version: str | None = None
    failure_code: str | None = None

    #: Present only on guest submissions, and only in the creation response.
    guest_token: str | None = None
    stored_original_text: bool = False
    disclaimers: list[str] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    id: uuid.UUID
    status: str
    source: str
    source_filename: str | None = None
    created_at: datetime
    label: str | None = None
    public_score: int | None = None
    reliability: str | None = None
    word_count: int


class AnalysisListResponse(BaseModel):
    items: list[AnalysisSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class AnalysisStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    failure_code: str | None = None


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    verdict: str = Field(pattern="^(agree|disagree|unsure)$")
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_id: uuid.UUID
    verdict: str
    comment: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    status: str
    created_at: datetime
    last_login_at: datetime | None
    suspended_at: datetime | None
    suspension_reason: str | None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class SuspendUserRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AdminStatsResponse(BaseModel):
    users_total: int
    users_active: int
    users_suspended: int
    analyses_total: int
    analyses_completed: int
    analyses_failed: int
    analyses_last_24h: int
    feedback_total: int


class SystemSettingResponse(BaseModel):
    key: str
    value: Any
    value_type: str
    description: str | None
    updated_at: datetime


class SystemSettingUpdate(BaseModel):
    value: Any


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    context: dict[str, Any] | None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Health & configuration
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    redis: str


class ModelHealthResponse(BaseModel):
    backend: str
    is_real_model: bool
    loaded: bool
    load_error_code: str | None = None
    load_error_detail: str | None = None
    model: dict[str, Any] | None = None


class PublicConfigResponse(BaseModel):
    product_name: str
    tagline: str
    support_email: str
    min_words: int
    low_reliability_words: int
    max_words: int
    max_characters: int
    max_upload_bytes: int
    allowed_extensions: list[str]
    bands: list[dict[str, Any]]
    disclaimers: list[str]
    guest_retention_hours: int
