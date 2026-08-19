"""Plain-text extraction with bounded, safe encoding detection."""

from __future__ import annotations

from charset_normalizer import from_bytes

from app.services.documents.base import (
    MAX_EXTRACTED_CHARACTERS,
    DocumentRejectedError,
    ExtractionResult,
)

#: Bytes inspected for encoding detection. Detection over a whole large file is
#: unnecessary work and a denial-of-service lever.
_DETECTION_SAMPLE_BYTES = 64 * 1024

#: A run of NUL bytes is the clearest marker of a binary file renamed to .txt.
_BINARY_MARKERS = (b"\x00\x00", b"\xff\xd8\xff", b"\x89PNG", b"PK\x03\x04", b"%PDF-")


def _looks_binary(payload: bytes) -> bool:
    if payload.startswith(_BINARY_MARKERS):
        return True
    if b"\x00" in payload[:_DETECTION_SAMPLE_BYTES]:
        return True
    sample = payload[:_DETECTION_SAMPLE_BYTES]
    if not sample:
        return False
    # A high share of non-text control bytes indicates binary content.
    control = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return control / len(sample) > 0.05


def extract_txt(payload: bytes) -> ExtractionResult:
    """Decode a plain-text upload, rejecting binary content."""
    if not payload.strip():
        raise DocumentRejectedError("empty_document", "The file is empty.")

    if _looks_binary(payload):
        raise DocumentRejectedError(
            "binary_content",
            "The .txt file contains binary data rather than readable text.",
        )

    notes: list[str] = []
    text: str | None = None

    # UTF-8 first: the overwhelmingly common case, and unambiguous when it works.
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        best = from_bytes(payload[:_DETECTION_SAMPLE_BYTES]).best()
        if best is None:
            raise DocumentRejectedError(
                "undecodable_text",
                "The file's character encoding could not be determined.",
            ) from None
        encoding = best.encoding
        try:
            text = payload.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            text = payload.decode(encoding, errors="replace")
            notes.append("Some characters could not be decoded and were replaced.")
        notes.append(f"Decoded using detected encoding '{encoding}'.")

    if len(text) > MAX_EXTRACTED_CHARACTERS:
        text = text[:MAX_EXTRACTED_CHARACTERS]
        notes.append("The document was truncated to the extraction limit.")

    if not text.strip():
        raise DocumentRejectedError("empty_document", "The file contains no readable text.")

    return ExtractionResult(text=text, notes=notes)
