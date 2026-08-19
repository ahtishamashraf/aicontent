"""Typed ORM models for OriginLens.

Design notes
------------
* Opaque tokens (sessions, guest access, verification, reset) are stored **only**
  as peppered digests. The plaintext exists solely in the client's possession.
* Submitted text is stored only when the submitter opts in, and always as an
  AES-256-GCM envelope in ``Analysis.encrypted_text``.
* Rate limiting and audit records never store a plaintext IP address.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Postgres ENUM that persists member *values* (``user``), not names."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
    )


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, enum.Enum):
    PENDING = "pending"  # registered, email not yet verified
    ACTIVE = "active"
    SUSPENDED = "suspended"


class AnalysisStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisSource(str, enum.Enum):
    TEXT = "text"
    DOCUMENT = "document"


class TokenPurpose(str, enum.Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"  # noqa: S105 - enum member, not a credential


class ReliabilityLevel(str, enum.Enum):
    INSUFFICIENT = "insufficient"
    LOW = "low"
    MODERATE = "moderate"
    NORMAL = "normal"


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _pg_enum(UserRole, "user_role"), default=UserRole.USER, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        _pg_enum(UserStatus, "user_status"), default=UserStatus.PENDING, nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(String(500))

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    tokens: Mapped[list[EmailToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Opaque server-side session. Only the token digest is persisted."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Coarse client descriptor for the user's own session list. Never an IP.
    user_agent_family: Mapped[str | None] = mapped_column(String(100))

    user: Mapped[User] = relationship(back_populates="sessions")


class EmailToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use, expiring verification or password-reset token (digest only)."""

    __tablename__ = "email_tokens"
    __table_args__ = (Index("ix_email_tokens_user_purpose", "user_id", "purpose"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    purpose: Mapped[TokenPurpose] = mapped_column(
        _pg_enum(TokenPurpose, "token_purpose"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="tokens")


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
class Analysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "public_score IS NULL OR (public_score >= 0 AND public_score <= 100)",
            name="public_score_range",
        ),
        CheckConstraint(
            "(user_id IS NOT NULL) OR (guest_token_hash IS NOT NULL)",
            name="owner_or_guest_required",
        ),
        Index("ix_analyses_user_created", "user_id", "created_at"),
    )

    #: Null for guest submissions.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: Digest of the guest access token; null for authenticated submissions.
    guest_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    guest_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[AnalysisStatus] = mapped_column(
        _pg_enum(AnalysisStatus, "analysis_status"),
        default=AnalysisStatus.QUEUED,
        nullable=False,
        index=True,
    )
    source: Mapped[AnalysisSource] = mapped_column(
        _pg_enum(AnalysisSource, "analysis_source"), default=AnalysisSource.TEXT, nullable=False
    )
    #: Original filename is stored escaped for display; never used as a path.
    source_filename: Mapped[str | None] = mapped_column(String(255))

    # --- Counts (safe metadata, not content) --------------------------------
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paragraph_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- Results -------------------------------------------------------------
    #: Raw aggregated model output in [0, 1], stored separately from the
    #: public-facing score so calibration can change without losing the source.
    raw_model_score: Mapped[float | None] = mapped_column(Float)
    public_score: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(60))
    reliability: Mapped[ReliabilityLevel | None] = mapped_column(
        _pg_enum(ReliabilityLevel, "reliability_level")
    )
    reliability_reasons: Mapped[list[str] | None] = mapped_column(JSONB)
    window_stability: Mapped[float | None] = mapped_column(Float)
    diagnostics: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    integrity_warnings: Mapped[list[str] | None] = mapped_column(JSONB)
    detected_language: Mapped[str | None] = mapped_column(String(16))
    language_confidence: Mapped[float | None] = mapped_column(Float)

    # --- Provenance ----------------------------------------------------------
    #: model_id, revision/commit, transformers + torch versions, device,
    #: calibration version, detector version. Never contains content.
    model_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    calibration_version: Mapped[str | None] = mapped_column(String(40))
    detector_version: Mapped[str | None] = mapped_column(String(40))

    # --- Failure reporting ---------------------------------------------------
    failure_code: Mapped[str | None] = mapped_column(String(60))

    # --- Optional retained content ------------------------------------------
    store_original_text: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encrypted_text: Mapped[bytes | None] = mapped_column(LargeBinary)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User | None] = relationship(back_populates="analyses")
    segments: Mapped[list[AnalysisSegment]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnalysisSegment.index",
    )
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", passive_deletes=True
    )


class AnalysisSegment(UUIDPrimaryKeyMixin, Base):
    """One paragraph of an analysis, in stable document order."""

    __tablename__ = "analysis_segments"
    __table_args__ = (UniqueConstraint("analysis_id", "index", name="uq_segment_order"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Null when the paragraph carries too little evidence to score honestly.
    raw_model_score: Mapped[float | None] = mapped_column(Float)
    public_score: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(60))
    #: True when the paragraph was grouped with neighbours or is too short.
    too_short: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grouped_with_context: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Retained only when the analysis retains original text.
    encrypted_text: Mapped[bytes | None] = mapped_column(LargeBinary)

    analysis: Mapped[Analysis] = relationship(back_populates="segments")


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analyses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    #: "agree" | "disagree" | "unsure"
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Free-text comment from the reviewer about the *result*, not the document.
    comment: Mapped[str | None] = mapped_column(Text)

    analysis: Mapped[Analysis] = relationship(back_populates="feedback")


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------
class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Administrative and security-relevant events. Never contains content."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_action_created", "action", "created_at"),)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(60))
    target_id: Mapped[str | None] = mapped_column(String(64))
    #: Privacy-preserving keyed digest of the client identifier, never an IP.
    actor_identifier_hash: Mapped[str | None] = mapped_column(String(64))
    #: Structured, content-free context (counts, codes, decisions).
    context: Mapped[dict[str, object] | None] = mapped_column(JSONB)


class SystemSetting(TimestampMixin, Base):
    """Typed, admin-editable runtime settings."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
