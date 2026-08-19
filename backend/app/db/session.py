"""Engine and session lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[OrmSession] | None = None


def get_engine() -> Engine:
    """Return the lazily-created process-wide engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            future=True,
            # Never echo SQL: bound parameters can contain submitted text.
            echo=False,
        )
    return _engine


def get_session_factory() -> sessionmaker[OrmSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False, future=True
        )
    return _session_factory


def reset_engine() -> None:
    """Dispose the engine. Used by tests and by worker fork hooks."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[OrmSession]:
    """Transactional scope for non-request contexts (workers, CLI)."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[OrmSession]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
