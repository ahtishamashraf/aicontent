"""Analysis lifecycle, authorization boundaries, and guest token handling."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from datetime import UTC

import build_fixtures as fx

from tests.integration.conftest import (
    ENGLISH_SAMPLE,
    csrf_headers,
    login,
    make_user,
)

pytestmark = pytest.mark.integration


def _submit_guest(client: TestClient, text: str = ENGLISH_SAMPLE):
    return client.post("/api/v1/analyses/text", json={"text": text})


class TestGuestTextAnalysis:
    def test_guest_submission_completes_and_returns_a_token(self, client: TestClient) -> None:
        response = _submit_guest(client)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "completed"
        assert body["guest_token"]
        assert 0 <= body["public_score"] <= 100
        assert body["label"]

    def test_result_carries_disclaimers(self, client: TestClient) -> None:
        body = _submit_guest(client).json()
        assert body["disclaimers"]
        assert any("not proof of authorship" in d for d in body["disclaimers"])

    def test_result_records_provenance(self, client: TestClient) -> None:
        body = _submit_guest(client).json()
        assert body["calibration_version"]
        assert body["detector_version"]
        assert body["model_metadata"]["backend"] == "fake"
        assert body["model_metadata"]["is_real_model"] is False

    def test_raw_and_public_scores_are_both_present_and_distinct_fields(
        self, client: TestClient
    ) -> None:
        body = _submit_guest(client).json()
        assert 0.0 <= body["raw_model_score"] <= 1.0
        assert body["public_score"] == round(body["raw_model_score"] * 100)

    def test_paragraph_segments_are_returned_in_order(self, client: TestClient) -> None:
        body = _submit_guest(client).json()
        indexes = [s["index"] for s in body["segments"]]
        assert indexes == sorted(indexes)
        assert body["counts"]["paragraphs"] == len(body["segments"])

    def test_short_text_is_reported_honestly(self, client: TestClient) -> None:
        body = _submit_guest(client, "Only a handful of words here today.").json()
        assert body["label"] == "Insufficient text"
        assert body["public_score"] is None
        assert body["reliability"] == "insufficient"

    def test_unsupported_language_is_reported(self, client: TestClient) -> None:
        # Comfortably above the minimum word count, so the language gate is what
        # rejects it rather than the length gate.
        french = (
            "Le comite a examine la proposition revisee avec beaucoup d attention "
            "pendant la session de mars et plusieurs membres ont exprime des "
            "inquietudes au sujet du calendrier de livraison propose par la "
            "direction generale du service concerne. La question du recrutement "
            "reste egalement ouverte car deux postes sont vacants depuis le mois "
            "de janvier dernier et la charge de travail repose desormais sur une "
            "equipe beaucoup plus reduite que prevu initialement par le plan. "
            "Le president a donc accepte de faire circuler un nouveau calendrier "
            "avant la prochaine reunion du comite directeur. Les archives posent "
            "un probleme different car les documents sources restent incoherents "
            "et personne ne sait vraiment comment les classer correctement. "
            "L archiviste propose donc une approche progressive pour traiter "
            "d abord les documents deja catalogues par le service competent."
        )
        assert len(french.split()) >= 80
        body = _submit_guest(client, french).json()
        assert body["label"] == "Unsupported language"
        assert body["public_score"] is None

    def test_guest_text_is_not_retained(self, client: TestClient, db: OrmSession) -> None:
        from app.db.models import Analysis

        _submit_guest(client)
        rows = db.execute(select(Analysis)).scalars().all()
        assert rows
        for row in rows:
            assert row.store_original_text is False
            assert row.encrypted_text is None

    def test_oversized_submission_is_refused(self, client: TestClient) -> None:
        response = _submit_guest(client, "word " * 40_000)
        assert response.status_code in (413, 422)


class TestGuestTokenBoundary:
    def test_result_is_readable_with_the_token(self, client: TestClient) -> None:
        created = _submit_guest(client).json()
        response = client.get(
            f"/api/v1/analyses/{created['id']}", params={"token": created["guest_token"]}
        )
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_result_is_not_readable_without_the_token(self, client: TestClient) -> None:
        created = _submit_guest(client).json()
        response = client.get(f"/api/v1/analyses/{created['id']}")
        assert response.status_code == 404

    def test_result_is_not_readable_with_a_wrong_token(self, client: TestClient) -> None:
        created = _submit_guest(client).json()
        response = client.get(f"/api/v1/analyses/{created['id']}", params={"token": "x" * 43})
        assert response.status_code == 404

    def test_expired_guest_token_is_refused(self, client: TestClient, db: OrmSession) -> None:
        from datetime import datetime, timedelta

        from app.db.models import Analysis

        created = _submit_guest(client).json()
        row = db.execute(select(Analysis)).scalars().one()
        row.guest_expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.add(row)
        db.commit()

        response = client.get(
            f"/api/v1/analyses/{created['id']}", params={"token": created["guest_token"]}
        )
        assert response.status_code == 404

    def test_only_the_token_digest_is_stored(self, client: TestClient, db: OrmSession) -> None:
        from app.db.models import Analysis

        created = _submit_guest(client).json()
        row = db.execute(select(Analysis)).scalars().one()
        assert row.guest_token_hash != created["guest_token"]
        assert len(row.guest_token_hash) == 64


class TestAuthenticatedAnalysis:
    def test_user_can_analyse_and_see_it_in_history(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="hist@example.com")
        login(client, user.email)

        created = client.post(
            "/api/v1/analyses/text",
            json={"text": ENGLISH_SAMPLE},
            headers=csrf_headers(client),
        )
        assert created.status_code == 201
        assert created.json()["guest_token"] is None

        listing = client.get("/api/v1/analyses").json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == created.json()["id"]

    def test_stored_text_is_encrypted_at_rest_and_recoverable(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.core.crypto import decrypt_text
        from app.db.models import Analysis

        user = make_user(db, email="store@example.com")
        login(client, user.email)
        client.post(
            "/api/v1/analyses/text",
            json={"text": ENGLISH_SAMPLE, "store_original_text": True},
            headers=csrf_headers(client),
        )

        row = db.execute(select(Analysis)).scalars().one()
        assert row.store_original_text is True
        assert row.encrypted_text is not None
        # The ciphertext must not contain the plaintext.
        assert b"committee reviewed" not in row.encrypted_text
        assert "committee reviewed" in decrypt_text(row.encrypted_text)

    def test_text_is_not_stored_when_not_requested(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import Analysis

        user = make_user(db, email="nostore@example.com")
        login(client, user.email)
        client.post(
            "/api/v1/analyses/text",
            json={"text": ENGLISH_SAMPLE},
            headers=csrf_headers(client),
        )
        row = db.execute(select(Analysis)).scalars().one()
        assert row.encrypted_text is None

    def test_history_supports_pagination_and_filtering(
        self, client: TestClient, db: OrmSession
    ) -> None:
        user = make_user(db, email="page@example.com")
        login(client, user.email)
        for _ in range(3):
            client.post(
                "/api/v1/analyses/text",
                json={"text": ENGLISH_SAMPLE},
                headers=csrf_headers(client),
            )

        page = client.get("/api/v1/analyses", params={"page": 1, "page_size": 2}).json()
        assert page["total"] == 3
        assert len(page["items"]) == 2
        assert page["total_pages"] == 2

        filtered = client.get("/api/v1/analyses", params={"status": "completed"}).json()
        assert filtered["total"] == 3
        assert client.get("/api/v1/analyses", params={"source": "document"}).json()["total"] == 0

    def test_deletion_removes_the_analysis_and_its_segments(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import Analysis, AnalysisSegment

        user = make_user(db, email="del@example.com")
        login(client, user.email)
        created = client.post(
            "/api/v1/analyses/text",
            json={"text": ENGLISH_SAMPLE},
            headers=csrf_headers(client),
        ).json()

        response = client.delete(f"/api/v1/analyses/{created['id']}", headers=csrf_headers(client))
        assert response.status_code == 200

        db.expunge_all()
        assert db.execute(select(Analysis)).scalars().all() == []
        assert db.execute(select(AnalysisSegment)).scalars().all() == []

    def test_delete_all_clears_history(self, client: TestClient, db: OrmSession) -> None:
        from app.db.models import Analysis

        user = make_user(db, email="delall@example.com")
        login(client, user.email)
        for _ in range(2):
            client.post(
                "/api/v1/analyses/text",
                json={"text": ENGLISH_SAMPLE},
                headers=csrf_headers(client),
            )

        assert client.delete("/api/v1/analyses", headers=csrf_headers(client)).status_code == 200
        db.expunge_all()
        assert db.execute(select(Analysis)).scalars().all() == []


class TestOwnershipBoundaries:
    def test_one_user_cannot_read_another_users_analysis(
        self, client: TestClient, db: OrmSession
    ) -> None:
        owner = make_user(db, email="owner@example.com")
        login(client, owner.email)
        created = client.post(
            "/api/v1/analyses/text",
            json={"text": ENGLISH_SAMPLE},
            headers=csrf_headers(client),
        ).json()
        client.post("/api/v1/auth/logout", headers=csrf_headers(client))

        intruder = make_user(db, email="intruder@example.com")
        login(client, intruder.email)

        assert client.get(f"/api/v1/analyses/{created['id']}").status_code == 404
        assert client.get(f"/api/v1/analyses/{created['id']}/status").status_code == 404

    def test_one_user_cannot_delete_another_users_analysis(
        self, client: TestClient, db: OrmSession
    ) -> None:
        from app.db.models import Analysis

        owner = make_user(db, email="owner2@example.com")
        login(client, owner.email)
        created = client.post(
            "/api/v1/analyses/text",
            json={"text": ENGLISH_SAMPLE},
            headers=csrf_headers(client),
        ).json()
        client.post("/api/v1/auth/logout", headers=csrf_headers(client))

        intruder = make_user(db, email="intruder2@example.com")
        login(client, intruder.email)
        response = client.delete(f"/api/v1/analyses/{created['id']}", headers=csrf_headers(client))
        assert response.status_code == 404

        db.expunge_all()
        assert db.execute(select(Analysis)).scalars().all() != []

    def test_history_requires_authentication(self, client: TestClient) -> None:
        assert client.get("/api/v1/analyses").status_code == 401


class TestDocumentAnalysis:
    def test_txt_upload_completes(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/analyses/document",
            files={"file": ("notes.txt", fx.valid_txt(40), "text/plain")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "completed"
        assert body["source"] == "document"
        assert body["source_filename"] == "notes.txt"

    def test_pdf_upload_completes(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/analyses/document",
            files={"file": ("report.pdf", fx.valid_pdf(pages=4), "application/pdf")},
        )
        assert response.status_code == 201
        assert response.json()["status"] == "completed"

    def test_docx_upload_completes(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/analyses/document",
            files={
                "file": (
                    "essay.docx",
                    fx.valid_docx(30),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert response.status_code == 201
        assert response.json()["status"] == "completed"

    @pytest.mark.parametrize(
        ("name", "payload"),
        [
            ("evil.docx", fx.traversal_docx()),
            ("bomb.docx", fx.zip_bomb_docx()),
            ("secret.pdf", fx.encrypted_pdf()),
            ("binary.txt", fx.binary_txt()),
        ],
    )
    def test_malicious_uploads_are_refused_safely(
        self, client: TestClient, name: str, payload: bytes
    ) -> None:
        response = client.post(
            "/api/v1/analyses/document",
            files={"file": (name, payload, "application/octet-stream")},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error"]["code"] == "document_rejected"
        assert "correlation_id" in body["error"]

    def test_disallowed_extension_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/analyses/document",
            files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_traversal_filename_is_stored_without_a_path(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/analyses/document",
            files={"file": ("../../../etc/passwd.txt", fx.valid_txt(40), "text/plain")},
        )
        assert response.status_code == 201
        assert response.json()["source_filename"] == "passwd.txt"


class TestFeedback:
    def test_guest_can_leave_feedback_with_their_token(self, client: TestClient) -> None:
        created = _submit_guest(client).json()
        response = client.post(
            f"/api/v1/analyses/{created['id']}/feedback",
            params={"token": created["guest_token"]},
            json={"verdict": "disagree", "comment": "This did not match my expectation."},
        )
        assert response.status_code == 201
        assert response.json()["verdict"] == "disagree"

    def test_feedback_without_access_is_refused(self, client: TestClient) -> None:
        created = _submit_guest(client).json()
        response = client.post(
            f"/api/v1/analyses/{created['id']}/feedback", json={"verdict": "agree"}
        )
        assert response.status_code == 404

    def test_invalid_verdict_is_rejected(self, client: TestClient) -> None:
        created = _submit_guest(client).json()
        response = client.post(
            f"/api/v1/analyses/{created['id']}/feedback",
            params={"token": created["guest_token"]},
            json={"verdict": "sabotage"},
        )
        assert response.status_code == 422
