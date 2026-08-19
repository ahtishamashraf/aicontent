"""Liveness, readiness, model health, and public configuration.

Liveness answers "is this process running". Readiness answers "can it serve
requests", which is a different question: a process with a broken database
connection is alive but not ready. Model readiness is separate again, because
the API can serve history and account routes while a worker's model is still
loading.
"""

from __future__ import annotations

import redis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbDep, SettingsDep
from app.api.schemas import (
    HealthResponse,
    ModelHealthResponse,
    PublicConfigResponse,
    ReadinessResponse,
)
from app.core.branding import DISCLAIMERS, PRODUCT_NAME, SUPPORT_EMAIL, TAGLINE
from app.core.ratelimit import get_redis
from app.services.documents import ALLOWED_EXTENSIONS
from detection.calibration import bands_as_dicts
from detection.registry import provider_status

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    """The process is running. Deliberately touches no dependency."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness(db: DbDep, response: Response) -> ReadinessResponse:
    """The process can reach its dependencies."""
    database = "ok"
    cache = "ok"

    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"

    try:
        get_redis().ping()
    except (redis.RedisError, OSError):
        cache = "unavailable"

    overall = "ready" if database == "ok" and cache == "ok" else "degraded"
    if overall != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(status=overall, database=database, redis=cache)


@router.get("/health/model", response_model=ModelHealthResponse)
def model_health(settings: SettingsDep) -> ModelHealthResponse:
    """Model readiness, reported separately from API readiness."""
    return ModelHealthResponse(**provider_status(settings))


@router.get("/config", response_model=PublicConfigResponse)
def public_config(settings: SettingsDep) -> PublicConfigResponse:
    """Public configuration. The backend is the source of truth for limits."""
    return PublicConfigResponse(
        product_name=PRODUCT_NAME,
        tagline=TAGLINE,
        support_email=SUPPORT_EMAIL,
        min_words=settings.min_words,
        low_reliability_words=settings.low_reliability_words,
        max_words=settings.max_words,
        max_characters=settings.max_characters,
        max_upload_bytes=settings.max_upload_bytes,
        allowed_extensions=sorted(ALLOWED_EXTENSIONS),
        bands=bands_as_dicts(),
        disclaimers=list(DISCLAIMERS),
        guest_retention_hours=settings.guest_retention_hours,
    )
