"""PDF text extraction with signature, encryption, and size guards.

External resources are never fetched: ``pypdf`` reads only the bytes provided,
and no annotation, embedded file, or JavaScript action is executed. Only text
is pulled from the page content streams.
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.documents.base import (
    MAX_EXTRACTED_CHARACTERS,
    MAX_PDF_PAGES,
    PDF_SIGNATURE,
    DocumentRejectedError,
    ExtractionResult,
)


def extract_pdf(payload: bytes) -> ExtractionResult:
    """Extract text from a PDF, refusing encrypted and malformed documents."""
    if not payload.startswith(PDF_SIGNATURE):
        raise DocumentRejectedError(
            "invalid_signature",
            "The file does not have a valid PDF signature.",
        )

    try:
        reader = PdfReader(io.BytesIO(payload), strict=False)
    except (PdfReadError, ValueError, OSError):
        raise DocumentRejectedError(
            "malformed_pdf", "The PDF could not be read; it may be corrupt."
        ) from None

    if reader.is_encrypted:
        # Some PDFs are "encrypted" with an empty owner password. Try that once;
        # anything requiring a real password is refused with a clear message.
        try:
            if reader.decrypt("") == 0:
                raise DocumentRejectedError(
                    "encrypted_pdf",
                    "This PDF is password-protected. Remove the protection and upload it again.",
                )
        except DocumentRejectedError:
            raise
        except Exception:
            raise DocumentRejectedError(
                "encrypted_pdf",
                "This PDF is password-protected. Remove the protection and upload it again.",
            ) from None

    notes: list[str] = []
    try:
        pages = reader.pages
        page_count = len(pages)
    except (PdfReadError, ValueError):
        raise DocumentRejectedError(
            "malformed_pdf", "The PDF page structure could not be read."
        ) from None

    if page_count == 0:
        raise DocumentRejectedError("empty_document", "The PDF contains no pages.")

    if page_count > MAX_PDF_PAGES:
        notes.append(f"Only the first {MAX_PDF_PAGES} pages were read.")

    chunks: list[str] = []
    total = 0
    for page in pages[:MAX_PDF_PAGES]:
        try:
            extracted = page.extract_text() or ""
        except Exception:
            notes.append("One or more pages could not be read and were skipped.")
            continue
        if not extracted:
            continue
        chunks.append(extracted)
        total += len(extracted)
        if total >= MAX_EXTRACTED_CHARACTERS:
            notes.append("The document was truncated to the extraction limit.")
            break

    text = "\n\n".join(chunks)[:MAX_EXTRACTED_CHARACTERS]

    if not text.strip():
        raise DocumentRejectedError(
            "no_extractable_text",
            "No text could be extracted. This PDF appears to contain scanned "
            "images, and optical character recognition is not supported.",
        )

    return ExtractionResult(text=text, notes=notes, page_count=page_count)
