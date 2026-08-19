"""Double-submit CSRF validation for state-changing requests.

The CSRF token is issued alongside the session. Its digest is stored on the
session row, and the plaintext is placed in a readable (non-HttpOnly) cookie
that the frontend echoes in the ``X-CSRF-Token`` header. A cross-site attacker
can cause the session cookie to be sent but cannot read the CSRF cookie to
construct the matching header.
"""

from __future__ import annotations

from app.core.security import constant_time_compare, hash_token
from app.db.models import Session as SessionModel

#: Methods that never change state and therefore need no CSRF token.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def requires_csrf(method: str) -> bool:
    return method.upper() not in SAFE_METHODS


def validate_csrf(session: SessionModel, supplied_token: str | None) -> bool:
    """Constant-time comparison of the supplied token against the session."""
    if not supplied_token:
        return False
    return constant_time_compare(hash_token(supplied_token), session.csrf_token_hash)
