"""Shared types and limits for document extraction."""

from __future__ import annotations

from dataclasses import dataclass, field

#: Accepted extensions. Anything else is refused before a byte is parsed.
ALLOWED_EXTENSIONS = frozenset({".txt", ".pdf", ".docx"})

#: Content signatures. Browser-supplied MIME types are never trusted.
PDF_SIGNATURE = b"%PDF-"
ZIP_SIGNATURE = b"PK\x03\x04"
#: Empty archives and spanned-archive markers also start with "PK".
ZIP_EMPTY_SIGNATURE = b"PK\x05\x06"
ZIP_SPANNED_SIGNATURE = b"PK\x07\x08"

#: Archive safety limits for DOCX (a ZIP container).
MAX_ZIP_MEMBERS = 512
MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024  # 80 MiB
MAX_COMPRESSION_RATIO = 120.0

#: Hard ceiling on extracted text handed to the analyser, independent of the
#: word/character limits applied later.
MAX_EXTRACTED_CHARACTERS = 400_000

#: PDF page ceiling: bounds work for a hostile document.
MAX_PDF_PAGES = 300


class DocumentRejectedError(Exception):
    """Raised when a document cannot be accepted.

    ``code`` is a short stable identifier; ``message`` is safe to show a user
    and never contains document content.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ExtractionResult:
    text: str
    #: Content-free notes about what was skipped or truncated.
    notes: list[str] = field(default_factory=list)
    page_count: int | None = None
