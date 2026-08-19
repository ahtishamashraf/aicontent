"""Administrator boundaries, rate limiting, and content-safety guarantees."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from tests.integration.conftest import (
    ENGLISH_SAMPLE,
    csrf_headers,
    login,
    make_user,
)

pytestmark = pytest.mark.integration

ADMIN_ROUTES = [
    ("GET", "/api/v1/admin/users"),
    ("GET", "/api/v1/admin/stats"),
    ("GET", "/api/v1/admin/feedback"),
    ("GET", "/api/v1/admin/settings"),
    ("GET", "/api/v1/admin/audit-logs"),
    ("GET", "/api/v1/admin/health/model"),
]


class TestAdminAuthorization:
    @pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
    def test_anonymous_callers_are_refused(
        self, client: TestClient, method: str, path: str
    ) -> None:
        assert client.request(method, path).status_code == 401

    @pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
    def test_ordinary_users_are_refused(
        self, client: TestClient, db: OrmSession, method: str, path: str
    ) -> None:
        user = make_user(db, email=f"plain{abs(hash(path)) % 9999}@example.com")
        login(client, user.email)
        response = client.request(method, path)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"

    @pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
    def test_administrators_are_allowed(
        self, client: TestClient, db: OrmSession, method: str, path: str
    ) -> None:
        admin = make_user(db, email=f"admin{abs(hash(path)) % 9999}@example.com", role="admin")
        login(client, admin.email)
        assert client.request(method, path).status_code == 200

    def test_suspended_admin_loses_access(self, client: TestClient, db: OrmSession) -> None:
        from app.db.models import User, UserStatus

        admin = make_user(db, email="suspadmin@example.com", role="admin")
        login(client, admin.email)
        assert client.get("/api/v1/admin/users").status_code == 200

        row = db.get(User, admin.id)
        assert row is not None
        row.status = UserStatus.SUSPENDED
        db.add(row)
        db.commit()

        assert client.get("/api/v1/admin/users").status_code == 403


class TestAdminOperations:
    def test_suspend_and_reactivate_a_user(self, client: TestClient, db: OrmSession) -> None:
        from app.db.models import User, UserStatus

        admin = make_user(db, email="ops@example.com", role="admin")
        target = make_user(db, email="target@example.com")
        login(client, admin.email)

        response = client.post(
            f"/api/v1/admin/users/{target.id}/suspend",
            json={"reason": "Repeated abuse of the analysis endpoint."},
            headers=csrf_headers(client),
        )
        assert response.status_code == 200

        db.expire_all()
        refreshed = db.get(User, target.id)
        assert refreshed is not None and refreshed.status is UserStatus.SUSPENDED
        assert refreshed.suspension_reason

        response = client.post(
            f"/api/v1/admin/users/{target.id}/reactivate", headers=csrf_headers(client)
        )
        assert response.status_code == 200
        db.expire_all()
        refreshed = db.get(User, target.id)
        assert refreshed is not None and refreshed.status is UserStatus.ACTIVE

    def test_suspension_revokes_the_targets_sessions(
        self, client: TestClient, db: OrmSession
    ) -> None:
        admin = make_user(db, email="ops2@example.com", role="admin")
        target = make_user(db, email="victim@example.com")

        target_client_cookies = None
        login(client, target.email)
        assert client.get("/api/v1/auth/session").status_code == 200
        target_client_cookies = dict(client.cookies)
        client.cookies.clear()

        login(client, admin.email)
        client.post(
            f"/api/v1/admin/users/{target.id}/suspend",
            json={"reason": "Policy violation."},
            headers=csrf_headers(client),
        )
        client.cookies.clear()

        for name, value in target_client_cookies.items():
            client.cookies.set(name, value)
        assert client.get("/api/v1/auth/session").status_code == 401

    def test_admin_cannot_suspend_themselves(self, client: TestClient, db: OrmSession) -> None:
        admin = make_user(db, email="self@example.com", role="admin")
        login(client, admin.email)
        response = client.post(
            f"/api/v1/admin/users/{admin.id}/suspend",
            json={"reason": "Testing self-suspension."},
            headers=csrf_headers(client),
        )
        assert response.status_code == 409

    def test_statistics_are_aggregate_only(self, client: TestClient, db: OrmSession) -> None:
        admin = make_user(db, email="stats@example.com", role="admin")
        login(client, admin.email)
        client.post(
            "/api/v1/analyses/text",
            json={"text": ENGLISH_SAMPLE},
            headers=csrf_headers(client),
        )

        body = client.get("/api/v1/admin/stats").json()
        assert body["analyses_total"] >= 1
        assert "committee reviewed" not in str(body)

    def test_audit_log_records_administrative_actions(
        self, client: TestClient, db: OrmSession
    ) -> None:
        admin = make_user(db, email="audit@example.com", role="admin")
        target = make_user(db, email="audited@example.com")
        login(client, admin.email)
        client.post(
            f"/api/v1/admin/users/{target.id}/suspend",
            json={"reason": "Policy violation."},
            headers=csrf_headers(client),
        )

        entries = client.get("/api/v1/admin/audit-logs").json()["items"]
        actions = {entry["action"] for entry in entries}
        assert "admin.user_suspended" in actions

    def test_admin_user_search_is_parameterised(self, client: TestClient, db: OrmSession) -> None:
        admin = make_user(db, email="search@example.com", role="admin")
        make_user(db, email="findme@example.com")
        login(client, admin.email)

        # A SQL metacharacter payload must be treated as a literal search string.
        injection = client.get("/api/v1/admin/users", params={"search": "'; DROP TABLE users; --"})
        assert injection.status_code == 200
        assert injection.json()["total"] == 0

        # The table is intact and ordinary search still works.
        found = client.get("/api/v1/admin/users", params={"search": "findme"})
        assert found.json()["total"] == 1


class TestRateLimiting:
    def test_login_attempts_are_limited(self, client: TestClient, db: OrmSession) -> None:
        user = make_user(db, email="brute@example.com")
        statuses = [login(client, user.email, "wrong-password-here").status_code for _ in range(14)]
        assert 429 in statuses, "credential stuffing must eventually be throttled"

    def test_rate_limited_response_carries_retry_after(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="retry@example.com")
        response = None
        for _ in range(14):
            response = login(client, user.email, "wrong-password-here")
            if response.status_code == 429:
                break
        assert response is not None and response.status_code == 429
        assert response.headers.get("Retry-After")
        assert response.json()["error"]["code"] == "rate_limited"

    def test_no_plaintext_ip_is_written_to_redis(self, client: TestClient) -> None:
        from app.core.ratelimit import get_redis

        client.post("/api/v1/analyses/text", json={"text": "short"})
        keys = list(get_redis().scan_iter("rl:*"))
        assert keys, "expected at least one rate-limit key"
        for key in keys:
            assert "testclient" not in key
            assert "127.0.0.1" not in key
            # policy name plus a 32-character digest
            assert len(key.rsplit(":", 1)[-1]) == 32

    def test_guest_analysis_is_limited(self, client: TestClient) -> None:
        statuses = [
            client.post("/api/v1/analyses/text", json={"text": ENGLISH_SAMPLE}).status_code
            for _ in range(8)
        ]
        assert 429 in statuses


class TestErrorEnvelopes:
    def test_every_error_has_a_correlation_id(self, client: TestClient) -> None:
        for response in (
            client.get("/api/v1/analyses"),
            client.get("/api/v1/admin/users"),
            client.get("/api/v1/analyses/00000000-0000-0000-0000-000000000000"),
        ):
            body = response.json()
            assert set(body["error"]) >= {"code", "message", "correlation_id"}
            assert body["error"]["correlation_id"] != "unknown"

    def test_errors_do_not_contain_stack_traces(self, client: TestClient) -> None:
        response = client.get("/api/v1/analyses/not-a-uuid")
        assert "Traceback" not in response.text
        assert "sqlalchemy" not in response.text.lower()
        assert 'File "' not in response.text

    def test_correlation_id_is_echoed_from_the_request(self, client: TestClient) -> None:
        response = client.get("/api/v1/health/live", headers={"X-Correlation-ID": "trace-abc-123"})
        assert response.headers["X-Correlation-ID"] == "trace-abc-123"

    def test_hostile_correlation_id_is_sanitised(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/health/live",
            headers={"X-Correlation-ID": "<script>alert(1)</script>"},
        )
        echoed = response.headers["X-Correlation-ID"]
        assert "<" not in echoed and ">" not in echoed


class TestContentSafety:
    def test_submitted_text_never_appears_in_logs(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        marker = "PINEAPPLE-SENTINEL-7731"
        text = f"{ENGLISH_SAMPLE} {marker}"
        with caplog.at_level("DEBUG"):
            response = client.post("/api/v1/analyses/text", json={"text": text})
        assert response.status_code == 201
        assert marker not in caplog.text

    def test_submitted_text_never_appears_in_audit_logs(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import AuditLog

        marker = "MANGO-SENTINEL-4412"
        user = make_user(db, email="auditsafe@example.com")
        login(client, user.email)
        client.post(
            "/api/v1/analyses/text",
            json={"text": f"{ENGLISH_SAMPLE} {marker}"},
            headers=csrf_headers(client),
        )

        entries = db.execute(select(AuditLog)).scalars().all()
        assert all(marker not in str(entry.context) for entry in entries)

    def test_rejection_errors_do_not_echo_submitted_text(self, client: TestClient) -> None:
        marker = "PAPAYA-SENTINEL-9090"
        response = client.post("/api/v1/analyses/text", json={"text": f"{marker} " * 400})
        assert marker not in response.text

    def test_security_headers_are_present(self, client: TestClient) -> None:
        headers = client.get("/api/v1/health/live").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        assert headers["Referrer-Policy"] == "no-referrer"
