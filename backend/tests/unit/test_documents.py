"""Document extraction security.

Fixtures are synthesised by ``tests/fixtures/build_fixtures.py`` so that hostile
cases are auditable as code rather than committed as opaque binaries. No real
user writing appears in any fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

import build_fixtures as fx

from app.services.documents import (
    DocumentRejectedError,
    extract_document,
    safe_display_filename,
)

MAX_BYTES = 5 * 1024 * 1024


def _extract(filename: str, payload: bytes, max_bytes: int = MAX_BYTES):
    return extract_document(filename, payload, max_bytes)


class TestAcceptedFormats:
    def test_plain_text_is_extracted(self) -> None:
        result = _extract("notes.txt", fx.valid_txt())
        assert "committee reviewed" in result.text

    def test_non_utf8_text_is_decoded_with_a_note(self) -> None:
        result = _extract("notes.txt", fx.latin1_txt())
        assert result.text
        assert any("encoding" in note for note in result.notes)

    def test_pdf_text_is_extracted(self) -> None:
        result = _extract("report.pdf", fx.valid_pdf())
        assert "committee reviewed" in result.text
        assert result.page_count == 1

    def test_multi_page_pdf_is_extracted(self) -> None:
        result = _extract("report.pdf", fx.valid_pdf(pages=3))
        assert result.page_count == 3

    def test_docx_paragraphs_are_extracted(self) -> None:
        result = _extract("essay.docx", fx.valid_docx())
        assert "committee reviewed" in result.text


class TestTypeValidation:
    @pytest.mark.parametrize("name", ["a.exe", "a.zip", "a.doc", "a.rtf", "a", "a.txt.exe"])
    def test_disallowed_extensions_are_refused(self, name: str) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract(name, b"anything at all")
        assert excinfo.value.code == "unsupported_type"

    def test_pdf_extension_with_non_pdf_content_is_refused(self) -> None:
        # Browser MIME and extension are not trusted; the signature decides.
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("fake.pdf", fx.valid_docx())
        assert excinfo.value.code == "invalid_signature"

    def test_docx_extension_with_non_zip_content_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("fake.docx", fx.valid_pdf())
        assert excinfo.value.code == "invalid_signature"


class TestSizeLimits:
    def test_oversized_upload_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("big.txt", b"x" * (MAX_BYTES + 1))
        assert excinfo.value.code == "file_too_large"

    def test_empty_upload_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("empty.txt", b"")
        assert excinfo.value.code == "empty_document"


class TestBinaryText:
    @pytest.mark.parametrize(
        ("name", "payload"),
        [("png", fx.binary_txt()), ("nuls", fx.nul_txt())],
    )
    def test_binary_content_in_txt_is_refused(self, name: str, payload: bytes) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("notes.txt", payload)
        assert excinfo.value.code == "binary_content"


class TestPdfSafety:
    def test_encrypted_pdf_is_refused_with_a_clear_message(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("secret.pdf", fx.encrypted_pdf())
        assert excinfo.value.code == "encrypted_pdf"
        assert "password-protected" in excinfo.value.message

    def test_scanned_pdf_explains_that_ocr_is_unsupported(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("scan.pdf", fx.scanned_pdf())
        assert excinfo.value.code == "no_extractable_text"
        assert "optical character recognition" in excinfo.value.message

    def test_malformed_pdf_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("broken.pdf", fx.malformed_pdf())
        assert excinfo.value.code == "malformed_pdf"


class TestDocxArchiveSafety:
    def test_path_traversal_member_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("evil.docx", fx.traversal_docx())
        assert excinfo.value.code == "unsafe_member_path"

    def test_absolute_path_member_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("evil.docx", fx.absolute_path_docx())
        assert excinfo.value.code == "unsafe_member_path"

    def test_symlink_member_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("evil.docx", fx.symlink_docx())
        assert excinfo.value.code == "symlink_member"

    def test_decompression_bomb_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("bomb.docx", fx.zip_bomb_docx())
        assert excinfo.value.code in {
            "suspicious_compression_ratio",
            "archive_too_large",
        }

    def test_excessive_member_count_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("many.docx", fx.many_members_docx())
        assert excinfo.value.code == "too_many_members"

    def test_zip_without_a_word_document_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("plain.docx", fx.not_a_word_docx())
        assert excinfo.value.code == "not_a_word_document"

    def test_malformed_archive_is_refused(self) -> None:
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("broken.docx", fx.malformed_zip())
        assert excinfo.value.code == "malformed_archive"


class TestFilenameSafety:
    @pytest.mark.parametrize(
        ("supplied", "expected"),
        [
            ("../../../etc/passwd.txt", "passwd.txt"),
            ("..\\..\\windows\\evil.docx", "evil.docx"),
            ("/absolute/path/file.pdf", "file.pdf"),
            ("plain.txt", "plain.txt"),
        ],
    )
    def test_directory_components_are_stripped(self, supplied: str, expected: str) -> None:
        assert safe_display_filename(supplied) == expected

    def test_length_is_bounded(self) -> None:
        assert len(safe_display_filename("a" * 500 + ".txt")) <= 255

    def test_nul_bytes_are_removed(self) -> None:
        assert "\x00" not in safe_display_filename("bad\x00name.txt")

    def test_empty_name_falls_back(self) -> None:
        assert safe_display_filename("   ") == "document"

    def test_traversal_filename_with_valid_content_is_neutralised_not_trusted(self) -> None:
        # The upload is accepted, but the stored name carries no path.
        result = _extract("../../../etc/passwd.txt", fx.valid_txt())
        assert result.text
        assert "/" not in safe_display_filename("../../../etc/passwd.txt")


class TestErrorSafety:
    def test_rejection_messages_carry_no_document_content(self) -> None:
        secret = b"CONFIDENTIAL-MARKER-9f3a " * 200
        with pytest.raises(DocumentRejectedError) as excinfo:
            _extract("secret.pdf", secret)
        assert "CONFIDENTIAL-MARKER" not in excinfo.value.message
        assert "CONFIDENTIAL-MARKER" not in excinfo.value.code
