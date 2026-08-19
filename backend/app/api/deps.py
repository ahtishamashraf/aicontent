"""Shared FastAPI dependencies: settings, database, session, and authorization."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session as OrmSession

from app.auth.csrf import requires_csrf, validate_csrf
from app.auth.sessions import (
    CSRF_HEADER,
    SESSION_COOKIE,
    is_idle_expired,
    load_session,
    touch_session,
)
from app.core.config import Settings, get_settings
from app.core.errors import (
    AuthenticationRequired,
    CsrfFailed,
    PermissionDenied,
    RateLimited,
)
from app.core.ratelimit import check_rate_limit
from app.db.models import User, UserStatus
from app.db.session import get_db


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]
DbDep = Annotated[OrmSession, Depends(get_db)]


def client_identifier(request: Request) -> str:
    """Return the raw client discriminator for rate limiting.

    This value is passed straight into a keyed digest and is never stored or
    logged in plaintext. ``request.client.host`` is used rather than a
    forwarded header unless the deployment is known to sit behind a trusted
    proxy, because a spoofable header would let an attacker evade limits.
    """
    return request.client.host if request.client else "unknown"


ClientIdDep = Annotated[str, Depends(client_identifier)]


def enforce_rate_limit(policy: str, request: Request, *, fail_closed: bool = False) -> None:
    """Apply ``policy`` to the current client, raising when exhausted."""
    result = check_rate_limit(policy, client_identifier(request), fail_closed=fail_closed)
    if not result.allowed:
        raise RateLimited(retry_after=result.retry_after)


def current_user_optional(request: Request, db: DbDep, settings: SettingsDep) -> User | None:
    """Resolve the signed-in user, or ``None`` for anonymous callers.

    Also enforces CSRF on state-changing requests and the session idle timeout.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    session = load_session(db, token)
    if session is None:
        return None

    if is_idle_expired(session, settings):
        return None

    if requires_csrf(request.method):
        supplied = request.headers.get(CSRF_HEADER)
        if not validate_csrf(session, supplied):
            raise CsrfFailed()

    user = session.user
    if user is None:
        return None

    touch_session(db, session)
    db.commit()

    # Expose the live session so routes can rotate or revoke it.
    request.state.session = session
    return user


OptionalUserDep = Annotated[User | None, Depends(current_user_optional)]


def current_user(user: OptionalUserDep) -> User:
    """Require an authenticated, active account."""
    if user is None:
        raise AuthenticationRequired()
    if user.status == UserStatus.SUSPENDED:
        raise PermissionDenied("This account is suspended.")
    if user.status == UserStatus.PENDING:
        raise PermissionDenied("Confirm your email address to continue.")
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]


def current_admin(user: CurrentUserDep) -> User:
    """Require an administrator. Checked server-side on every admin route."""
    if not user.is_admin:
        raise PermissionDenied()
    return user


AdminDep = Annotated[User, Depends(current_admin)]


def db_transaction(db: DbDep) -> Iterator[OrmSession]:
    """Commit on success, roll back on failure."""
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
