"""Secure document extraction.

Dispatch validates the extension and the content signature; the browser-supplied
MIME type is only ever advisory. Extraction happens entirely in memory, so no
temporary file is written for an attacker to race or for a failed request to
leave behind.
"""

from __future__ import annotations

import os

from app.services.documents.base import (
    ALLOWED_EXTENSIONS,
    DocumentRejectedError,
    ExtractionResult,
)
from app.services.documents.docx import extract_docx
from app.services.documents.pdf import extract_pdf
from app.services.documents.txt import extract_txt

__all__ = [
    "ALLOWED_EXTENSIONS",
    "DocumentRejectedError",
    "ExtractionResult",
    "extract_document",
    "safe_display_filename",
]

_EXTRACTORS = {".txt": extract_txt, ".pdf": extract_pdf, ".docx": extract_docx}


def safe_display_filename(filename: str) -> str:
    """Return a filename safe to store and display.

    The uploaded name is never used as a filesystem path. Directory components
    are stripped and the result is bounded; escaping for HTML is the renderer's
    responsibility.
    """
    base = os.path.basename(filename.replace("\\", "/")).strip()
    base = base.replace("\x00", "")
    return base[:255] or "document"


def extension_of(filename: str) -> str:
    return os.path.splitext(safe_display_filename(filename))[1].lower()


def extract_document(filename: str, payload: bytes, max_bytes: int) -> ExtractionResult:
    """Validate and extract text from an uploaded document."""
    if len(payload) > max_bytes:
        raise DocumentRejectedError(
            "file_too_large",
            f"The file exceeds the {max_bytes // (1024 * 1024)} MiB upload limit.",
        )
    if not payload:
        raise DocumentRejectedError("empty_document", "The file is empty.")

    extension = extension_of(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentRejectedError(
            "unsupported_type",
            "Only .txt, .pdf, and .docx files are accepted.",
        )

    return _EXTRACTORS[extension](payload)
