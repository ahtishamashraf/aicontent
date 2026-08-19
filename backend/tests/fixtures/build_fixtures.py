"""Generate document fixtures, including hostile ones, for the test suite.

Fixtures are synthesised here rather than committed as binaries so that the
repository never carries opaque blobs, and so the hostile cases are auditable
as code. No real user writing is used anywhere.
"""

from __future__ import annotations

import io
import zipfile

LOREM = (
    "The committee reviewed the revised proposal during the March session and "
    "several members raised concerns about the delivery timeline for the work. "
)

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>{paragraphs}</w:body></w:document>"
)
_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)


def valid_txt(repeats: int = 20) -> bytes:
    return (LOREM * repeats).encode("utf-8")


def latin1_txt() -> bytes:
    return ("Café façade naïve résumé. " + LOREM * 10).encode("latin-1")


def binary_txt() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 20


def nul_txt() -> bytes:
    return b"some text\x00\x00with embedded nulls" + b"\x00" * 100


def _assemble_pdf(objects: list[bytes], trailer_extra: str = "") -> bytes:
    """Write a structurally valid PDF with a correct xref table."""
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R {trailer_extra}>>\n"
        f"startxref\n{xref_at}\n%%EOF"
    ).encode()
    return bytes(out)


def valid_pdf(pages: int = 1) -> bytes:
    """A minimal but genuinely parseable PDF with extractable text."""
    text = LOREM * 3
    objects: list[bytes] = []
    page_refs = " ".join(f"{4 + i * 2} 0 R" for i in range(pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {pages} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i in range(pages):
        stream = f"BT /F1 12 Tf 40 750 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {5 + i * 2} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    return _assemble_pdf(objects)


def encrypted_pdf() -> bytes:
    """A structurally valid PDF declaring standard security handler encryption."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
        b"<< /Filter /Standard /V 1 /R 2 /O <"
        + b"41" * 32
        + b"> /U <"
        + b"42" * 32
        + b"> /P -44 >>",
    ]
    trailer = "/Encrypt 4 0 R /ID [<" + "31" * 16 + "> <" + "32" * 16 + ">] "
    return _assemble_pdf(objects, trailer_extra=trailer)


def malformed_pdf() -> bytes:
    return b"%PDF-1.4\nthis is not actually a pdf structure at all\n%%EOF"


def scanned_pdf() -> bytes:
    """Structurally valid PDF whose page carries no text operators (a scan)."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    return _assemble_pdf(objects)


def _docx_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def valid_docx(paragraphs: int = 12) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{LOREM}</w:t></w:r></w:p>" for _ in range(paragraphs))
    return _docx_bytes(
        {
            "[Content_Types].xml": _CONTENT_TYPES.encode(),
            "_rels/.rels": _RELS.encode(),
            "word/document.xml": _DOCUMENT_XML.format(paragraphs=body).encode(),
        }
    )


def traversal_docx() -> bytes:
    return _docx_bytes(
        {
            "[Content_Types].xml": _CONTENT_TYPES.encode(),
            "_rels/.rels": _RELS.encode(),
            "word/document.xml": _DOCUMENT_XML.format(paragraphs="").encode(),
            "../../../../etc/passwd": b"root:x:0:0:root:/root:/bin/bash\n",
        }
    )


def absolute_path_docx() -> bytes:
    return _docx_bytes(
        {
            "[Content_Types].xml": _CONTENT_TYPES.encode(),
            "word/document.xml": _DOCUMENT_XML.format(paragraphs="").encode(),
            "/etc/shadow": b"nope",
        }
    )


def zip_bomb_docx() -> bytes:
    """A member that expands enormously from a tiny compressed payload."""
    return _docx_bytes(
        {
            "[Content_Types].xml": _CONTENT_TYPES.encode(),
            "word/document.xml": _DOCUMENT_XML.format(paragraphs="").encode(),
            "word/bomb.bin": b"\x00" * (60 * 1024 * 1024),
        }
    )


def many_members_docx() -> bytes:
    members = {
        "[Content_Types].xml": _CONTENT_TYPES.encode(),
        "word/document.xml": _DOCUMENT_XML.format(paragraphs="").encode(),
    }
    for i in range(600):
        members[f"word/extra_{i}.xml"] = b"<x/>"
    return _docx_bytes(members)


def symlink_docx() -> bytes:
    """An archive member flagged as a symbolic link via its Unix mode."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("word/document.xml", _DOCUMENT_XML.format(paragraphs=""))
        info = zipfile.ZipInfo("word/link")
        info.external_attr = (0xA1FF) << 16  # S_IFLNK | 0777
        archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()


def not_a_word_docx() -> bytes:
    """A valid ZIP that is not a Word document."""
    return _docx_bytes({"readme.txt": b"just a zip file"})


def malformed_zip() -> bytes:
    return b"PK\x03\x04" + b"garbage bytes that are not a zip structure" * 10
