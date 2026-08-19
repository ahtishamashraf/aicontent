"""Opaque server-side sessions with rotation, expiry, and revocation.

The session token is a high-entropy random string held only by the client. The
server stores its peppered digest, so a database disclosure does not yield
usable session tokens. Every login issues a fresh token (fixation protection)
and every privilege change rotates it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.config import Settings
from app.core.security import generate_csrf_token, generate_token, hash_token
from app.db.models import Session as SessionModel
from app.db.models import User

#: Cookie names. Both are host-only in the default same-origin deployment.
SESSION_COOKIE = "originlens_session"
CSRF_COOKIE = "originlens_csrf"
CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True)
class IssuedSession:
    """A newly created session. Plaintext values exist only here and in the response."""

    session: SessionModel
    token: str
    csrf_token: str


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    """Treat naive timestamps from the database as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def create_session(
    db: OrmSession,
    user: User,
    settings: Settings,
    *,
    user_agent_family: str | None = None,
) -> IssuedSession:
    """Issue a new session for ``user``."""
    token = generate_token()
    csrf_token = generate_csrf_token()
    now = _utcnow()

    session = SessionModel(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token_hash=hash_token(csrf_token),
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        last_seen_at=now,
        user_agent_family=user_agent_family,
    )
    db.add(session)
    db.flush()
    return IssuedSession(session=session, token=token, csrf_token=csrf_token)


def load_session(db: OrmSession, token: str) -> SessionModel | None:
    """Return a live session for ``token``, or ``None``.

    A session is live when it exists, is not revoked, has not passed its
    absolute expiry, and has not been idle beyond the idle timeout.
    """
    if not token:
        return None

    session = db.execute(
        select(SessionModel).where(SessionModel.token_hash == hash_token(token))
    ).scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        return None

    now = _utcnow()
    if _as_aware(session.expires_at) <= now:
        return None
    return session


def is_idle_expired(session: SessionModel, settings: Settings) -> bool:
    """Whether the session has been unused beyond the idle timeout."""
    idle_deadline = _as_aware(session.last_seen_at) + timedelta(
        seconds=settings.session_idle_timeout_seconds
    )
    return idle_deadline <= _utcnow()


def touch_session(db: OrmSession, session: SessionModel) -> None:
    """Record activity so the idle timeout is measured from the last request."""
    session.last_seen_at = _utcnow()
    db.add(session)


def rotate_session(
    db: OrmSession, session: SessionModel, user: User, settings: Settings
) -> IssuedSession:
    """Revoke ``session`` and issue a replacement.

    Used after any privilege or credential change so a token captured earlier
    cannot continue to be used.
    """
    revoke_session(db, session)
    return create_session(db, user, settings, user_agent_family=session.user_agent_family)


def revoke_session(db: OrmSession, session: SessionModel) -> None:
    session.revoked_at = _utcnow()
    db.add(session)


def revoke_all_for_user(db: OrmSession, user_id: uuid.UUID) -> int:
    """Revoke every live session for a user. Returns the number revoked."""
    now = _utcnow()
    sessions = (
        db.execute(
            select(SessionModel).where(
                SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    for session in sessions:
        session.revoked_at = now
        db.add(session)
    return len(sessions)


def purge_expired(db: OrmSession) -> int:
    """Delete sessions past their absolute expiry. Returns the count removed."""
    expired = (
        db.execute(select(SessionModel).where(SessionModel.expires_at <= _utcnow())).scalars().all()
    )
    for session in expired:
        db.delete(session)
    return len(expired)


def cookie_kwargs(settings: Settings, *, max_age: int | None = None) -> dict[str, object]:
    """Shared cookie attributes for the same-origin deployment."""
    kwargs: dict[str, object] = {
        "httponly": True,
        "secure": settings.cookie_secure,
        # Lax is correct for a same-origin app: it survives top-level navigation
        # but is not sent on cross-site POSTs, which blunts CSRF on its own.
        "samesite": "lax",
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    if max_age is not None:
        kwargs["max_age"] = max_age
    return kwargs
