"""Authentication lifecycle against real PostgreSQL and Redis."""

from __future__ import annotations

from datetime import UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from tests.integration.conftest import PASSWORD, csrf_headers, login, make_user

pytestmark = pytest.mark.integration


class TestRegistration:
    def test_registration_creates_a_pending_account(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import User, UserStatus

        response = client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": PASSWORD},
        )
        assert response.status_code == 202

        user = db.execute(select(User).where(User.email == "new@example.com")).scalar_one()
        assert user.status is UserStatus.PENDING
        assert user.email_verified_at is None

    def test_password_hash_is_argon2id_and_not_the_password(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import User

        client.post(
            "/api/v1/auth/register",
            json={"email": "hash@example.com", "password": PASSWORD},
        )
        user = db.execute(select(User).where(User.email == "hash@example.com")).scalar_one()
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash

    def test_duplicate_registration_does_not_reveal_the_existing_account(
        self, client: TestClient, db: OrmSession
    ) -> None:
        make_user(db, email="taken@example.com")
        first = client.post(
            "/api/v1/auth/register",
            json={"email": "fresh@example.com", "password": PASSWORD},
        )
        second = client.post(
            "/api/v1/auth/register",
            json={"email": "taken@example.com", "password": PASSWORD},
        )
        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()

    def test_short_password_is_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register", json={"email": "a@example.com", "password": "short"}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_failed"

    def test_validation_errors_do_not_echo_the_password(self, client: TestClient) -> None:
        secret = "abc"
        response = client.post(
            "/api/v1/auth/register", json={"email": "a@example.com", "password": secret}
        )
        assert secret not in response.text


class TestVerification:
    def test_verification_activates_the_account(self, client: TestClient, db: OrmSession) -> None:
        from app.auth.tokens import issue_token
        from app.db.models import TokenPurpose, User, UserStatus

        user = make_user(db, email="verify@example.com", status="pending")
        token = issue_token(db, user, TokenPurpose.EMAIL_VERIFICATION)
        db.commit()

        response = client.post("/api/v1/auth/verify", json={"token": token})
        assert response.status_code == 200

        db.expire_all()
        refreshed = db.get(User, user.id)
        assert refreshed is not None
        assert refreshed.status is UserStatus.ACTIVE
        assert refreshed.email_verified_at is not None

    def test_verification_token_is_single_use(self, client: TestClient, db: OrmSession) -> None:
        from app.auth.tokens import issue_token
        from app.db.models import TokenPurpose

        user = make_user(db, email="once@example.com", status="pending")
        token = issue_token(db, user, TokenPurpose.EMAIL_VERIFICATION)
        db.commit()

        assert client.post("/api/v1/auth/verify", json={"token": token}).status_code == 200
        assert client.post("/api/v1/auth/verify", json={"token": token}).status_code == 422

    def test_unknown_token_is_rejected(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/verify", json={"token": "x" * 43})
        assert response.status_code == 422

    def test_only_the_digest_is_stored(self, db: OrmSession) -> None:
        from app.auth.tokens import issue_token
        from app.db.models import EmailToken, TokenPurpose

        user = make_user(db, email="digest@example.com", status="pending")
        token = issue_token(db, user, TokenPurpose.EMAIL_VERIFICATION)
        db.commit()

        stored = db.execute(select(EmailToken)).scalars().all()
        assert all(row.token_hash != token for row in stored)
        assert all(len(row.token_hash) == 64 for row in stored)


class TestLogin:
    def test_login_issues_session_and_csrf_cookies(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="login@example.com")
        response = login(client, user.email)
        assert response.status_code == 200
        assert response.json()["email"] == user.email
        assert client.cookies.get("originlens_session")
        assert client.cookies.get("originlens_csrf")

    def test_session_cookie_is_httponly_and_the_token_is_not_stored_raw(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import Session as SessionModel

        user = make_user(db, email="cookie@example.com")
        response = login(client, user.email)
        set_cookie = response.headers.get("set-cookie", "")
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie.replace("samesite", "SameSite")

        token = client.cookies.get("originlens_session")
        rows = db.execute(select(SessionModel)).scalars().all()
        assert rows and all(row.token_hash != token for row in rows)

    def test_wrong_password_is_rejected_generically(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="wrong@example.com")
        response = login(client, user.email, "not-the-password-at-all")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_unknown_account_returns_the_same_error_as_a_wrong_password(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="known@example.com")
        unknown = login(client, "nobody@example.com", PASSWORD)
        wrong = login(client, user.email, "wrong-password-entirely")
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"]
        assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]

    def test_unverified_account_cannot_sign_in(self, client: TestClient, db: OrmSession) -> None:
        user = make_user(db, email="pending@example.com", status="pending")
        assert login(client, user.email).status_code == 401

    def test_suspended_account_is_told_why(self, client: TestClient, db: OrmSession) -> None:
        user = make_user(db, email="susp@example.com", status="suspended")
        response = login(client, user.email)
        assert response.status_code == 403
        assert "suspended" in response.json()["error"]["message"].lower()

    def test_login_rotates_the_session_token(self, client: TestClient, db: OrmSession) -> None:
        user = make_user(db, email="rotate@example.com")
        login(client, user.email)
        first = client.cookies.get("originlens_session")
        login(client, user.email)
        second = client.cookies.get("originlens_session")
        assert first != second


class TestSessionLifecycle:
    def test_anonymous_session_returns_a_null_user_not_an_error(self, client: TestClient) -> None:
        # 200 with user=null, so an anonymous page load does not log a console
        # error on every request.
        response = client.get("/api/v1/auth/session")
        assert response.status_code == 200
        assert response.json()["user"] is None

    def test_profile_never_exposes_the_password_hash(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="profile@example.com")
        login(client, user.email)
        body = client.get("/api/v1/auth/session").json()["user"]
        assert "password_hash" in dir(user)
        assert "password_hash" not in body
        assert "password" not in body

    def test_logout_revokes_the_session_server_side(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="logout@example.com")
        login(client, user.email)
        token = client.cookies.get("originlens_session")

        assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 200

        # Even replaying the old cookie fails: revocation is server-side.
        client.cookies.set("originlens_session", token or "")
        assert client.get("/api/v1/auth/session").json()["user"] is None

    def test_revoked_session_cannot_be_reused(self, client: TestClient, db: OrmSession) -> None:
        from app.auth.sessions import revoke_all_for_user

        user = make_user(db, email="revoked@example.com")
        login(client, user.email)
        assert client.get("/api/v1/auth/session").json()["user"] is not None

        revoke_all_for_user(db, user.id)
        db.commit()
        assert client.get("/api/v1/auth/session").json()["user"] is None

    def test_expired_session_is_refused(self, client: TestClient, db: OrmSession) -> None:
        from datetime import datetime, timedelta

        from app.db.models import Session as SessionModel

        user = make_user(db, email="expired@example.com")
        login(client, user.email)

        session = db.execute(
            select(SessionModel).where(SessionModel.user_id == user.id)
        ).scalar_one()
        session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.add(session)
        db.commit()

        assert client.get("/api/v1/auth/session").json()["user"] is None


class TestCsrf:
    def test_state_change_without_a_csrf_token_is_refused(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="csrf@example.com")
        login(client, user.email)

        response = client.post(
            "/api/v1/auth/password/change",
            json={"current_password": PASSWORD, "new_password": "another-long-password-9"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_failed"

    def test_state_change_with_a_wrong_csrf_token_is_refused(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="csrf2@example.com")
        login(client, user.email)

        response = client.post(
            "/api/v1/auth/password/change",
            json={"current_password": PASSWORD, "new_password": "another-long-password-9"},
            headers={"X-CSRF-Token": "forged-token-value"},
        )
        assert response.status_code == 403

    def test_state_change_with_the_matching_token_succeeds(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="csrf3@example.com")
        login(client, user.email)

        response = client.post(
            "/api/v1/auth/password/change",
            json={"current_password": PASSWORD, "new_password": "another-long-password-9"},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200

    def test_safe_methods_do_not_require_a_csrf_token(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="csrf4@example.com")
        login(client, user.email)
        assert client.get("/api/v1/auth/session").json()["user"] is not None


class TestPasswordReset:
    def test_forgot_password_does_not_reveal_whether_the_account_exists(
        self, client: TestClient, db: OrmSession
    ) -> None:
        make_user(db, email="real@example.com")
        known = client.post("/api/v1/auth/password/forgot", json={"email": "real@example.com"})
        unknown = client.post("/api/v1/auth/password/forgot", json={"email": "ghost@example.com"})
        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json()

    def test_reset_sets_the_password_and_revokes_sessions(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.auth.tokens import issue_token
        from app.db.models import TokenPurpose

        user = make_user(db, email="reset@example.com")
        login(client, user.email)
        assert client.get("/api/v1/auth/session").status_code == 200

        token = issue_token(db, user, TokenPurpose.PASSWORD_RESET)
        db.commit()

        new_password = "a-brand-new-password-123"
        response = client.post(
            "/api/v1/auth/password/reset", json={"token": token, "password": new_password}
        )
        assert response.status_code == 200

        # The old session is gone and the new password works.
        assert client.get("/api/v1/auth/session").json()["user"] is None
        assert login(client, user.email, new_password).status_code == 200

    def test_reset_token_is_single_use(self, client: TestClient, db: OrmSession) -> None:
        from app.auth.tokens import issue_token
        from app.db.models import TokenPurpose

        user = make_user(db, email="single@example.com")
        token = issue_token(db, user, TokenPurpose.PASSWORD_RESET)
        db.commit()

        first = client.post(
            "/api/v1/auth/password/reset", json={"token": token, "password": "new-password-abc-1"}
        )
        second = client.post(
            "/api/v1/auth/password/reset", json={"token": token, "password": "new-password-abc-2"}
        )
        assert first.status_code == 200
        assert second.status_code == 422

    def test_expired_reset_token_is_refused(self, client: TestClient, db: OrmSession) -> None:
        from datetime import datetime, timedelta

        from app.auth.tokens import issue_token
        from app.db.models import EmailToken, TokenPurpose

        user = make_user(db, email="stale@example.com")
        token = issue_token(db, user, TokenPurpose.PASSWORD_RESET)
        row = db.execute(select(EmailToken)).scalars().one()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.add(row)
        db.commit()

        response = client.post(
            "/api/v1/auth/password/reset", json={"token": token, "password": "another-password-1"}
        )
        assert response.status_code == 422


class TestAccountDeletion:
    def test_account_deletion_removes_the_user_and_their_analyses(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import Analysis, User

        user = make_user(db, email="bye@example.com")
        login(client, user.email)
        client.post(
            "/api/v1/analyses/text",
            json={"text": "word " * 200},
            headers=csrf_headers(client),
        )

        response = client.delete("/api/v1/auth/account", headers=csrf_headers(client))
        assert response.status_code == 200

        # Drop the identity map so these are genuine reads, not cached objects.
        db.expunge_all()
        assert db.get(User, user.id) is None
        remaining = db.execute(select(Analysis).where(Analysis.user_id == user.id)).scalars().all()
        assert remaining == []
