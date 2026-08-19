"""Integration fixtures backed by real PostgreSQL and Redis.

Each test runs against a schema created by the Alembic migrations, not by
``metadata.create_all``: that way the tests exercise the same DDL a deployment
would apply, and a migration that drifts from the models fails here.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

TEST_DB_URL = os.environ.get(
    "ORIGINLENS_TEST_DATABASE_URL",
    "postgresql+psycopg://originlens:originlens@127.0.0.1:5433/originlens_it",
)
ADMIN_DB_URL = os.environ.get(
    "ORIGINLENS_ADMIN_DATABASE_URL",
    "postgresql+psycopg://originlens:originlens@127.0.0.1:5433/postgres",
)

pytestmark = pytest.mark.integration


def _postgres_available() -> bool:
    try:
        engine = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _postgres_available(), reason="PostgreSQL is not reachable"
)


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    """Create a disposable database and migrate it with Alembic."""
    if not _postgres_available():
        pytest.skip("PostgreSQL is not reachable")

    name = TEST_DB_URL.rsplit("/", 1)[-1]
    admin = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()

    os.environ["ORIGINLENS_DATABASE_URL"] = TEST_DB_URL
    os.environ["ORIGINLENS_ENVIRONMENT"] = "test"
    os.environ["ORIGINLENS_DETECTOR_BACKEND"] = "fake"
    os.environ["ORIGINLENS_COOKIE_SECURE"] = "false"

    from alembic import command
    from alembic.config import Config
    from app.core.config import get_settings

    get_settings.cache_clear()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(config, "head")

    yield

    admin = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def engine():  # type: ignore[no-untyped-def]
    from app.db.session import get_engine, reset_engine

    reset_engine()
    yield get_engine()
    reset_engine()


@pytest.fixture(autouse=True)
def _clean_tables(_database: None) -> Iterator[None]:
    """Truncate between tests so each starts from a known state."""
    from app.db.session import get_engine

    yield
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "TRUNCATE users, sessions, email_tokens, analyses, "
                "analysis_segments, feedback, audit_logs, system_settings "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def db() -> Iterator[OrmSession]:
    from app.db.session import get_engine

    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    """Clear rate-limit counters so ordering cannot make tests flaky."""
    from app.core.ratelimit import get_redis, reset_redis

    try:
        redis_client = get_redis()
        for key in redis_client.scan_iter("rl:*"):
            redis_client.delete(key)
    except Exception:
        pass
    yield
    reset_redis()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ENGLISH_SAMPLE = (
    "The committee reviewed the revised proposal during the March session, and "
    "several members raised concerns about the delivery timeline. In particular, "
    "the assumption that procurement would complete before the summer recess "
    "struck two of them as optimistic. The chair agreed to circulate a revised "
    "schedule before the next meeting.\n\n"
    "A second matter concerned staffing levels across the department. Two "
    "vacancies have gone unfilled since January, and the resulting workload has "
    "fallen on a team smaller than the original plan assumed. Recruitment is "
    "under way, but suitable candidates remain scarce in this specialism, and "
    "the salary band has not moved in three years.\n\n"
    "Finally, the group discussed the archive migration. Progress has been slow "
    "because the source records are inconsistent: some are catalogued by "
    "accession number, others by donor, and a handful by nothing at all. The "
    "archivist proposed a triage approach, tackling the catalogued material "
    "first and setting aside the remainder for a later phase."
)

PASSWORD = "correct-horse-battery-staple-42"


def make_user(
    db: OrmSession,
    *,
    email: str | None = None,
    role: str = "user",
    status: str = "active",
    password: str = PASSWORD,
):  # type: ignore[no-untyped-def]
    """Create a user directly, bypassing the registration flow."""
    from app.core.security import hash_password
    from app.db.models import User, UserRole, UserStatus

    user = User(
        email=email or f"user-{uuid.uuid4().hex[:10]}@example.com",
        password_hash=hash_password(password),
        role=UserRole(role),
        status=UserStatus(status),
        email_verified_at=datetime.now(UTC) if status == "active" else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client: TestClient, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    """Log in and return the response, leaving cookies on the client."""
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def csrf_headers(client: TestClient) -> dict[str, str]:
    """Echo the readable CSRF cookie into the header, as the frontend does."""
    token = client.cookies.get("originlens_csrf")
    return {"X-CSRF-Token": token} if token else {}
