"""Analysis persistence and the job state machine.

The worker and the API share this module so that a job's lifecycle has exactly
one implementation. State transitions are validated: a completed analysis can
never be reopened, and a retried task cannot double-process a finished job.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.branding import DISCLAIMERS
from app.core.config import Settings
from app.core.crypto import encrypt_text
from app.core.security import generate_token, hash_token
from app.db.models import (
    Analysis,
    AnalysisSegment,
    AnalysisSource,
    AnalysisStatus,
    ReliabilityLevel,
    User,
)
from detection.pipeline import AnalysisResult

#: Transitions the state machine permits. Anything else is refused.
ALLOWED_TRANSITIONS: dict[AnalysisStatus, frozenset[AnalysisStatus]] = {
    AnalysisStatus.QUEUED: frozenset({AnalysisStatus.RUNNING, AnalysisStatus.FAILED}),
    AnalysisStatus.RUNNING: frozenset({AnalysisStatus.COMPLETED, AnalysisStatus.FAILED}),
    AnalysisStatus.COMPLETED: frozenset(),
    AnalysisStatus.FAILED: frozenset(),
}


class InvalidTransition(Exception):
    """Raised when a job is moved between incompatible states."""


def can_transition(current: AnalysisStatus, target: AnalysisStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition(analysis: Analysis, target: AnalysisStatus) -> None:
    """Move ``analysis`` to ``target``, refusing invalid moves."""
    if analysis.status == target:
        return
    if not can_transition(analysis.status, target):
        raise InvalidTransition(
            f"Cannot move analysis from {analysis.status.value} to {target.value}"
        )
    analysis.status = target
    now = datetime.now(UTC)
    if target is AnalysisStatus.RUNNING:
        analysis.started_at = now
    elif target in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
        analysis.completed_at = now


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_analysis(
    db: OrmSession,
    settings: Settings,
    *,
    user: User | None,
    source: AnalysisSource,
    source_filename: str | None = None,
    store_original_text: bool = False,
) -> tuple[Analysis, str | None]:
    """Create a queued analysis. Returns the row and a guest token when anonymous."""
    guest_token: str | None = None
    analysis = Analysis(
        user_id=user.id if user else None,
        status=AnalysisStatus.QUEUED,
        source=source,
        source_filename=source_filename,
        store_original_text=store_original_text and user is not None,
    )

    if user is None:
        guest_token = generate_token()
        analysis.guest_token_hash = hash_token(guest_token)
        analysis.guest_expires_at = _utcnow() + timedelta(hours=settings.guest_retention_hours)
        # Guests never retain content: there is no account to govern it.
        analysis.store_original_text = False

    db.add(analysis)
    db.flush()
    return analysis, guest_token


def apply_result(
    db: OrmSession,
    analysis: Analysis,
    result: AnalysisResult,
    *,
    display_text: str | None = None,
) -> None:
    """Persist a completed pipeline result onto ``analysis``."""
    analysis.word_count = result.word_count
    analysis.character_count = result.character_count
    analysis.paragraph_count = result.paragraph_count
    analysis.raw_model_score = result.raw_model_score
    analysis.public_score = result.public_score
    analysis.label = result.label
    analysis.reliability = ReliabilityLevel(result.reliability)
    analysis.reliability_reasons = result.reliability_reasons
    analysis.window_stability = result.window_stability
    analysis.diagnostics = result.diagnostics or None
    analysis.integrity_warnings = [w["code"] for w in result.integrity_warnings] or None
    analysis.detected_language = result.detected_language
    analysis.language_confidence = result.language_confidence
    analysis.model_metadata = result.model_metadata or None
    analysis.calibration_version = result.calibration_version
    analysis.detector_version = result.detector_version

    if analysis.store_original_text and display_text:
        analysis.encrypted_text = encrypt_text(display_text)

    # Replace segments wholesale so a retry cannot duplicate them.
    for existing in list(analysis.segments):
        db.delete(existing)
    db.flush()

    for segment in result.segments:
        db.add(
            AnalysisSegment(
                analysis_id=analysis.id,
                index=segment.index,
                word_count=segment.word_count,
                character_count=segment.character_count,
                raw_model_score=segment.raw_score,
                public_score=segment.public_score,
                label=segment.label,
                too_short=segment.too_short,
                grouped_with_context=segment.grouped_with_context,
                encrypted_text=(
                    encrypt_text(segment.text)
                    if analysis.store_original_text and segment.text
                    else None
                ),
            )
        )

    transition(analysis, AnalysisStatus.COMPLETED)
    db.add(analysis)


def mark_failed(db: OrmSession, analysis: Analysis, failure_code: str) -> None:
    """Record a bounded failure code. Never stores exception text."""
    analysis.failure_code = failure_code[:60]
    if analysis.status in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING):
        transition(analysis, AnalysisStatus.FAILED)
    db.add(analysis)


def load_for_owner(db: OrmSession, analysis_id: uuid.UUID, user: User) -> Analysis | None:
    """Load an analysis the user owns. Ownership is enforced in the query."""
    return db.execute(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user.id)
    ).scalar_one_or_none()


def load_for_guest(db: OrmSession, analysis_id: uuid.UUID, token: str) -> Analysis | None:
    """Load a guest analysis by id *and* token, refusing expired access."""
    if not token:
        return None
    analysis = db.execute(
        select(Analysis).where(
            Analysis.id == analysis_id,
            Analysis.guest_token_hash == hash_token(token),
        )
    ).scalar_one_or_none()

    if analysis is None or analysis.guest_expires_at is None:
        return None

    expires_at = analysis.guest_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= _utcnow():
        return None
    return analysis


def delete_analysis(db: OrmSession, analysis: Analysis) -> None:
    """Delete an analysis and every dependent row, including stored content."""
    db.delete(analysis)


def delete_all_for_user(db: OrmSession, user: User) -> int:
    """Delete every analysis owned by ``user``. Returns the count removed."""
    analyses = db.execute(select(Analysis).where(Analysis.user_id == user.id)).scalars().all()
    for analysis in analyses:
        db.delete(analysis)
    return len(analyses)


def purge_expired_guest_analyses(db: OrmSession) -> int:
    """Remove guest analyses past their retention window."""
    expired = (
        db.execute(
            select(Analysis).where(
                Analysis.guest_token_hash.is_not(None),
                Analysis.guest_expires_at <= _utcnow(),
            )
        )
        .scalars()
        .all()
    )
    for analysis in expired:
        db.delete(analysis)
    return len(expired)


def purge_expired_analyses(db: OrmSession, settings: Settings) -> int:
    """Remove analyses older than the configured retention period."""
    cutoff = _utcnow() - timedelta(days=settings.analysis_retention_days)
    expired = db.execute(select(Analysis).where(Analysis.created_at <= cutoff)).scalars().all()
    for analysis in expired:
        db.delete(analysis)
    return len(expired)


def count_for_user(db: OrmSession, user: User) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Analysis).where(Analysis.user_id == user.id)
        ).scalar_one()
    )


def disclaimers() -> list[str]:
    """Disclaimers attached to every result payload."""
    return list(DISCLAIMERS)
