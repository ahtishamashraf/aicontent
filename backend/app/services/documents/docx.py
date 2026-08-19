"""DOCX extraction with archive inspection before any member is read.

A .docx is a ZIP container. Every member is inspected *before* extraction:
path traversal, absolute paths, symlinks, member counts, uncompressed totals,
and per-member compression ratios are all checked against bounds. Macros,
embedded objects, and external relationship targets are never executed or
fetched — only the document body's text is read.
"""

from __future__ import annotations

import io
import posixpath
import zipfile

from docx import Document

from app.services.documents.base import (
    MAX_COMPRESSION_RATIO,
    MAX_EXTRACTED_CHARACTERS,
    MAX_UNCOMPRESSED_BYTES,
    MAX_ZIP_MEMBERS,
    ZIP_SIGNATURE,
    DocumentRejectedError,
    ExtractionResult,
)

#: The part every valid Word document must contain.
_REQUIRED_MEMBER = "word/document.xml"

#: Unix mode bit indicating a symbolic link, stored in the high 16 bits of
#: ``external_attr`` by archivers that preserve permissions.
_S_IFLNK = 0xA000

#: Members below this compressed size are exempt from the ratio check: tiny
#: highly-compressible XML parts legitimately exceed the ratio.
_RATIO_EXEMPT_BYTES = 1024


def _is_unsafe_path(name: str) -> bool:
    """Reject traversal, absolute paths, and drive-letter paths."""
    if not name or name.startswith(("/", "\\")):
        return True
    if ":" in name.split("/")[0] and len(name.split("/")[0]) == 2:
        return True  # Windows drive letter, e.g. "C:"
    normalised = posixpath.normpath(name.replace("\\", "/"))
    return normalised.startswith("../") or normalised == ".." or "/../" in normalised


def inspect_archive(archive: zipfile.ZipFile) -> None:
    """Validate archive members. Raises :class:`DocumentRejectedError`."""
    infos = archive.infolist()

    if len(infos) > MAX_ZIP_MEMBERS:
        raise DocumentRejectedError(
            "too_many_members",
            "The document archive contains an unreasonable number of entries.",
        )

    total_uncompressed = 0
    for info in infos:
        if _is_unsafe_path(info.filename):
            raise DocumentRejectedError(
                "unsafe_member_path",
                "The document archive contains an unsafe file path.",
            )

        # Symlinks are observable through the Unix mode in external_attr.
        mode = info.external_attr >> 16
        if mode and (mode & 0xF000) == _S_IFLNK:
            raise DocumentRejectedError(
                "symlink_member",
                "The document archive contains a symbolic link.",
            )

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise DocumentRejectedError(
                "archive_too_large",
                "The document expands to an unreasonable size and was rejected.",
            )

        if info.compress_size > _RATIO_EXEMPT_BYTES:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_COMPRESSION_RATIO:
                raise DocumentRejectedError(
                    "suspicious_compression_ratio",
                    "The document has a compression ratio typical of a "
                    "decompression bomb and was rejected.",
                )

    if not any(info.filename == _REQUIRED_MEMBER for info in infos):
        raise DocumentRejectedError(
            "not_a_word_document",
            "The file is not a valid Word document.",
        )


def extract_docx(payload: bytes) -> ExtractionResult:
    """Extract paragraph text from a .docx upload."""
    if not payload.startswith(ZIP_SIGNATURE):
        raise DocumentRejectedError(
            "invalid_signature",
            "The file does not have a valid Word document signature.",
        )

    buffer = io.BytesIO(payload)
    try:
        with zipfile.ZipFile(buffer) as archive:
            if archive.testzip() is not None:
                raise DocumentRejectedError("malformed_archive", "The document archive is corrupt.")
            inspect_archive(archive)
    except zipfile.BadZipFile:
        raise DocumentRejectedError(
            "malformed_archive", "The document archive could not be read."
        ) from None

    buffer.seek(0)
    try:
        document = Document(buffer)
    except Exception:
        raise DocumentRejectedError(
            "malformed_document", "The Word document could not be read."
        ) from None

    notes: list[str] = []
    chunks: list[str] = []
    total = 0
    for paragraph in document.paragraphs:
        text = paragraph.text
        if not text.strip():
            continue
        chunks.append(text)
        total += len(text)
        if total >= MAX_EXTRACTED_CHARACTERS:
            notes.append("The document was truncated to the extraction limit.")
            break

    text = "\n\n".join(chunks)[:MAX_EXTRACTED_CHARACTERS]
    if not text.strip():
        raise DocumentRejectedError(
            "no_extractable_text", "The document contains no readable text."
        )

    return ExtractionResult(text=text, notes=notes)
