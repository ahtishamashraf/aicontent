"""Declarative base and shared column conventions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Explicit naming convention so Alembic autogenerates stable constraint names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Project declarative base."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """UUID primary key generated application-side."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Creation and update timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
