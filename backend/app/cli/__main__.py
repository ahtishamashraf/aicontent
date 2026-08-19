"""Administrative command line.

Usage::

    python -m app.cli create-admin --email admin@example.com
    python -m app.cli seed-settings
    python -m app.cli retention-sweep
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.models import SystemSetting, User, UserRole, UserStatus
from app.db.session import session_scope

#: Settings seeded on a fresh deployment so the admin console has content.
DEFAULT_SETTINGS: tuple[tuple[str, object, str, str], ...] = (
    (
        "guest_analysis_enabled",
        True,
        "bool",
        "Allow analysis without an account.",
    ),
    (
        "registration_enabled",
        True,
        "bool",
        "Allow new accounts to be created.",
    ),
    (
        "maintenance_message",
        "",
        "str",
        "Banner shown to every visitor when non-empty.",
    ),
)

MIN_PASSWORD_LENGTH = 12


def _prompt_password() -> str:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        raise SystemExit(2)
    if len(first) < MIN_PASSWORD_LENGTH:
        print(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return first


def create_admin(email: str, password: str | None) -> int:
    """Create or promote an administrator account."""
    password = password or _prompt_password()
    normalised = email.strip().lower()

    with session_scope() as db:
        existing = db.execute(select(User).where(User.email == normalised)).scalar_one_or_none()

        if existing is not None:
            existing.role = UserRole.ADMIN
            existing.status = UserStatus.ACTIVE
            existing.email_verified_at = existing.email_verified_at or datetime.now(UTC)
            existing.password_hash = hash_password(password)
            db.add(existing)
            print(f"Promoted {normalised} to administrator.")
            return 0

        db.add(
            User(
                email=normalised,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                email_verified_at=datetime.now(UTC),
            )
        )
        print(f"Created administrator {normalised}.")
        return 0


def seed_settings() -> int:
    """Insert default system settings that do not already exist."""
    created = 0
    with session_scope() as db:
        for key, value, value_type, description in DEFAULT_SETTINGS:
            if db.get(SystemSetting, key) is not None:
                continue
            db.add(
                SystemSetting(
                    key=key,
                    value={"value": value},
                    value_type=value_type,
                    description=description,
                )
            )
            created += 1
    print(f"Seeded {created} setting(s).")
    return 0


def retention_sweep() -> int:
    """Run the retention sweep synchronously, without a worker."""
    from app.tasks.analysis_tasks import retention_sweep as task

    result = task.run()
    print(
        "Retention sweep removed: "
        f"{result['guest_analyses_removed']} guest analyses, "
        f"{result['aged_analyses_removed']} aged analyses, "
        f"{result['sessions_removed']} expired sessions."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging(get_settings().log_level)

    parser = argparse.ArgumentParser(prog="originlens", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    admin_parser = subparsers.add_parser("create-admin", help="Create or promote an admin")
    admin_parser.add_argument("--email", required=True)
    admin_parser.add_argument(
        "--password",
        default=None,
        help="Omit to be prompted. Passing a password puts it in your shell history.",
    )

    subparsers.add_parser("seed-settings", help="Insert default system settings")
    subparsers.add_parser("retention-sweep", help="Delete expired data now")

    args = parser.parse_args(argv)

    if args.command == "create-admin":
        return create_admin(args.email, args.password)
    if args.command == "seed-settings":
        return seed_settings()
    if args.command == "retention-sweep":
        return retention_sweep()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
