"""Single-use, expiring email verification and password-reset tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.core.security import generate_token, hash_token
from app.db.models import EmailToken, TokenPurpose, User

#: Verification links stay valid for a day; reset links for an hour.
TOKEN_TTL = {
    TokenPurpose.EMAIL_VERIFICATION: timedelta(hours=24),
    TokenPurpose.PASSWORD_RESET: timedelta(hours=1),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def issue_token(db: OrmSession, user: User, purpose: TokenPurpose) -> str:
    """Create a token for ``purpose``, invalidating any earlier unused one."""
    outstanding = (
        db.execute(
            select(EmailToken).where(
                EmailToken.user_id == user.id,
                EmailToken.purpose == purpose,
                EmailToken.consumed_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    now = _utcnow()
    for token in outstanding:
        token.consumed_at = now
        db.add(token)

    plaintext = generate_token()
    db.add(
        EmailToken(
            user_id=user.id,
            token_hash=hash_token(plaintext),
            purpose=purpose,
            expires_at=now + TOKEN_TTL[purpose],
        )
    )
    db.flush()
    return plaintext


def consume_token(db: OrmSession, plaintext: str, purpose: TokenPurpose) -> EmailToken | None:
    """Validate and consume a token. Returns ``None`` when unusable."""
    if not plaintext:
        return None

    token = db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(plaintext),
            EmailToken.purpose == purpose,
        )
    ).scalar_one_or_none()

    if token is None or token.consumed_at is not None:
        return None

    expires_at = (
        token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=UTC)
    )
    if expires_at <= _utcnow():
        return None

    token.consumed_at = _utcnow()
    db.add(token)
    return token
