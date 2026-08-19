"""Audit logging for administrative and security-relevant events.

Records carry identifiers, action codes, and structured context only. Submitted
text, passwords, tokens, and plaintext IP addresses are never written.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session as OrmSession

from app.core.logging import SENSITIVE_KEYS
from app.db.models import AuditLog


def record(
    db: OrmSession,
    action: str,
    *,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_identifier_hash: str | None = None,
    context: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit record. Sensitive context keys are dropped, not stored."""
    safe_context = None
    if context:
        safe_context = {k: v for k, v in context.items() if k.lower() not in SENSITIVE_KEYS}

    entry = AuditLog(
        created_at=datetime.now(UTC),
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor_identifier_hash=actor_identifier_hash,
        context=safe_context,
    )
    db.add(entry)
    return entry
