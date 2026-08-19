"""FastAPI application factory.

Middleware order matters: the correlation-ID middleware runs outermost so that
every response — including error envelopes produced deeper in the stack — can
carry the identifier that ties it to a log line.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.branding import PRODUCT_NAME
from app.core.config import Settings, get_settings
from app.core.errors import (
    AppError,
    ValidationFailed,
    app_error_handler,
    error_body,
    unhandled_error_handler,
)
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)

CORRELATION_HEADER = "X-Correlation-ID"

#: Applied to every response. The API serves JSON only, so the policy can be
#: maximally restrictive: nothing should ever be loaded from an API response.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), interest-cohort=()",
    "Content-Security-Policy": (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "api starting",
        extra={
            "event": "startup",
            "environment": settings.environment,
            "detector_backend": settings.detector_backend,
        },
    )
    yield
    logger.info("api stopping", extra={"event": "shutdown"})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application."""
    settings = settings or get_settings()

    app = FastAPI(
        title=f"{PRODUCT_NAME} API",
        version="1.0.0",
        description=(
            "Signals about how writing was produced. Scores are estimates, not "
            "proof of authorship."
        ),
        lifespan=lifespan,
        # Interactive docs are useful in development and noise in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Host allow-listing is a production control; development uses many hosts.
    if settings.is_production:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        max_age=600,
    )

    @app.middleware("http")
    async def correlate_and_secure(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        # Bound and sanitise: this value is echoed back to the client.
        correlation_id = "".join(c for c in correlation_id if c.isalnum() or c in "-_")[:64] or str(
            uuid.uuid4()
        )
        request.state.correlation_id = correlation_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers[CORRELATION_HEADER] = correlation_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        # The path can contain opaque identifiers but never content.
        logger.info(
            "request",
            extra={
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "correlation_id": correlation_id,
            },
        )
        return response

    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Report a validation failure without echoing the submitted values.

        FastAPI's default handler includes the offending input, which for this
        API would mean returning a slice of the user's document.
        """
        fields = sorted(
            {".".join(str(part) for part in error.get("loc", ())[1:]) for error in exc.errors()}
        )
        return JSONResponse(
            status_code=ValidationFailed.status_code,
            content=error_body(
                ValidationFailed.code,
                ValidationFailed.message,
                getattr(request.state, "correlation_id", "unknown"),
                fields=[f for f in fields if f],
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {
            401: "authentication_required",
            403: "permission_denied",
            404: "not_found",
            405: "method_not_allowed",
            413: "payload_too_large",
            429: "rate_limited",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                codes.get(exc.status_code, "request_failed"),
                str(exc.detail) if isinstance(exc.detail, str) else "The request failed.",
                getattr(request.state, "correlation_id", "unknown"),
            ),
        )

    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(api_router)
    return app


app = create_app()
