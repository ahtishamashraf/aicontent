"""Redis-backed rate limiting with privacy-preserving identifiers.

A plaintext IP address is never stored. The limiter keys on an HMAC-SHA256
digest of the client identifier under a server-side pepper, truncated to 128
bits. The digest is not reversible, and rotating ``ORIGINLENS_RATE_LIMIT_PEPPER``
invalidates every stored identifier.

Counters use a fixed window implemented with ``INCR`` + ``EXPIRE``, which is
atomic enough for abuse control and far cheaper than a sorted-set sliding
window. When Redis is unreachable the limiter fails **open** for ordinary
traffic but the caller decides: authentication routes pass ``fail_closed=True``
so an outage cannot become an unlimited credential-stuffing window.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
from dataclasses import dataclass

import redis

from app.core.config import get_settings

#: Truncated digest length in hex characters (128 bits).
_IDENTIFIER_LENGTH = 32

_client: redis.Redis[str] | None = None


@dataclass(frozen=True)
class RateLimitPolicy:
    """A named limit: ``limit`` events per ``window_seconds``."""

    name: str
    limit: int
    window_seconds: int


#: Policies for sensitive operations. Tuned for abuse control, not throughput.
POLICIES: dict[str, RateLimitPolicy] = {
    "guest_analysis": RateLimitPolicy("guest_analysis", limit=5, window_seconds=3600),
    "user_analysis": RateLimitPolicy("user_analysis", limit=60, window_seconds=3600),
    "login": RateLimitPolicy("login", limit=10, window_seconds=900),
    "register": RateLimitPolicy("register", limit=5, window_seconds=3600),
    "password_reset": RateLimitPolicy("password_reset", limit=5, window_seconds=3600),
    "verification_resend": RateLimitPolicy("verification_resend", limit=5, window_seconds=3600),
    "feedback": RateLimitPolicy("feedback", limit=20, window_seconds=3600),
    "admin_mutation": RateLimitPolicy("admin_mutation", limit=120, window_seconds=3600),
    "upload": RateLimitPolicy("upload", limit=20, window_seconds=3600),
}


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int


def get_redis() -> redis.Redis[str]:
    """Return the process-wide Redis client."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


def reset_redis() -> None:
    """Drop the cached client. Used by tests and worker fork hooks."""
    global _client
    if _client is not None:
        # Teardown must not raise: a failed close still leaves the client unusable.
        with contextlib.suppress(Exception):
            _client.close()
    _client = None


def identifier_digest(raw_identifier: str) -> str:
    """Return the privacy-preserving digest of a client identifier.

    ``raw_identifier`` may be an IP address, a user id, or any other client
    discriminator. Only the digest ever leaves this function.
    """
    pepper = get_settings().rate_limit_pepper.encode("utf-8")
    digest = hmac.new(pepper, raw_identifier.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:_IDENTIFIER_LENGTH]


def check_rate_limit(
    policy_name: str, raw_identifier: str, *, fail_closed: bool = False
) -> RateLimitResult:
    """Consume one unit of ``policy_name`` for ``raw_identifier``."""
    policy = POLICIES.get(policy_name)
    if policy is None:
        raise KeyError(f"Unknown rate limit policy '{policy_name}'")

    key = f"rl:{policy.name}:{identifier_digest(raw_identifier)}"

    try:
        client = get_redis()
        pipeline = client.pipeline()
        pipeline.incr(key)
        pipeline.ttl(key)
        raw_count, raw_ttl = pipeline.execute()
        count = int(raw_count)
        ttl = int(raw_ttl)

        if ttl < 0:
            client.expire(key, policy.window_seconds)
            ttl = policy.window_seconds
    except redis.RedisError:
        # The limiter is unavailable. Authentication paths must not silently
        # become unlimited, so they opt into failing closed.
        if fail_closed:
            return RateLimitResult(allowed=False, remaining=0, retry_after=60)
        return RateLimitResult(allowed=True, remaining=policy.limit, retry_after=0)

    if count > policy.limit:
        return RateLimitResult(allowed=False, remaining=0, retry_after=max(ttl, 1))

    return RateLimitResult(allowed=True, remaining=max(policy.limit - count, 0), retry_after=0)


def reset_policy(policy_name: str, raw_identifier: str) -> None:
    """Clear a counter, e.g. after a successful login."""
    policy = POLICIES.get(policy_name)
    if policy is None:
        return
    try:
        get_redis().delete(f"rl:{policy.name}:{identifier_digest(raw_identifier)}")
    except redis.RedisError:
        return
