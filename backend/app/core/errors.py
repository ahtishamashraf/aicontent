"""Safe, uniform error envelopes.

Every failure leaves the API as ``{"error": {"code", "message", "correlation_id"}}``.
Messages are curated constants — never exception text, stack traces, SQL, or any
fragment of submitted content.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for errors that are safe to surface to clients."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "The request could not be processed."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}


class ValidationFailed(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_failed"
    message = "The submitted values are not valid."


class AuthenticationRequired(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_required"
    message = "Authentication is required."


class InvalidCredentials(AppError):
    """Deliberately generic: prevents account enumeration."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class PermissionDenied(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have access to this resource."


class CsrfFailed(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "csrf_failed"
    message = "The security token is missing or invalid. Reload the page and try again."


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The resource is in a conflicting state."


class PayloadTooLarge(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "payload_too_large"
    message = "The submission exceeds the configured size limit."


class UnsupportedMedia(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"
    message = "Only .txt, .pdf, and .docx files are accepted."


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Please wait before trying again."

    def __init__(self, retry_after: int = 60, message: str | None = None):
        super().__init__(message, details={"retry_after": retry_after})
        self.retry_after = retry_after


class DocumentRejected(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "document_rejected"
    message = "The document could not be processed safely."


class AnalysisUnavailable(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "analysis_unavailable"
    message = "Analysis is temporarily unavailable. Please try again shortly."


class InternalError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"
    message = "An unexpected error occurred."


def error_body(code: str, message: str, correlation_id: str, **extra: Any) -> dict[str, Any]:
    """Build the canonical error envelope."""
    payload: dict[str, Any] = {
        "error": {"code": code, "message": message, "correlation_id": correlation_id}
    }
    if extra:
        payload["error"].update(extra)
    return payload


def correlation_id_of(request: Request) -> str:
    """Return the correlation ID attached by the request middleware."""
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, str) else "unknown"


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render :class:`AppError` instances as safe envelopes."""
    assert isinstance(exc, AppError)
    headers = {}
    if isinstance(exc, RateLimited):
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, correlation_id_of(request), **exc.details),
        headers=headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render any unexpected error without leaking internals."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body(InternalError.code, InternalError.message, correlation_id_of(request)),
    )
