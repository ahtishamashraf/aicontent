"""Password hashing, opaque token handling, and CSRF primitives.

No cryptography is invented here. Password hashing uses Argon2id via
``argon2-cffi``; token digests use SHA-256 over a server-side pepper; CSRF
tokens are compared in constant time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

#: Argon2id parameters. Chosen for interactive login on modest CPU hardware.
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

#: Length in bytes of opaque session / verification / guest tokens.
TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Return an Argon2id hash for ``password``."""
    return _HASHER.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify ``password`` against ``stored_hash`` without raising."""
    try:
        return _HASHER.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    """Report whether ``stored_hash`` uses outdated Argon2 parameters."""
    try:
        return _HASHER.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return False


def generate_token() -> str:
    """Return a fresh, URL-safe opaque token. Only its digest is stored."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return the peppered SHA-256 digest of an opaque token.

    Tokens are already high-entropy, so a fast digest is appropriate; the
    pepper prevents offline correlation if the database alone is disclosed.
    """
    pepper = get_settings().secret_key.encode("utf-8")
    return hmac.new(pepper, token.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_compare(left: str, right: str) -> bool:
    """Constant-time string comparison."""
    return hmac.compare_digest(left, right)


def generate_csrf_token() -> str:
    """Return a new CSRF token value."""
    return secrets.token_urlsafe(32)
