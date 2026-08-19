"""Background analysis tasks.

Tasks are idempotent: a retry that finds the job already completed returns
without redoing the work, and the state machine refuses to reopen a terminal
job. Document text is passed by database reference rather than through the
queue, so submitted content never lands in Redis or in queue metadata.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import get_settings
from app.core.crypto import DecryptionError, decrypt_text
from app.db.models import Analysis, AnalysisStatus
from app.db.session import session_scope
from app.services import analysis as analysis_service
from app.tasks.worker import celery_app
from detection.engines.base import DetectorError
from detection.pipeline import InputRejected, analyse
from detection.registry import get_provider

logger = logging.getLogger(__name__)


@celery_app.task(
    name="originlens.analyse",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
    autoretry_for=(),
)
def run_analysis(self: Any, analysis_id: str) -> dict[str, str]:
    """Analyse a queued submission.

    Only the analysis id crosses the queue. The text is read from the encrypted
    column inside the worker, so the payload in Redis is a UUID and nothing else.
    """
    settings = get_settings()
    identifier = uuid.UUID(analysis_id)

    with session_scope() as db:
        analysis = db.get(Analysis, identifier)
        if analysis is None:
            logger.warning(
                "analysis missing", extra={"event": "task_missing", "analysis_id": analysis_id}
            )
            return {"analysis_id": analysis_id, "status": "missing"}

        # Idempotency: a redelivered message must not reprocess a finished job.
        if analysis.status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED):
            return {"analysis_id": analysis_id, "status": analysis.status.value}

        if analysis.encrypted_text is None:
            analysis_service.mark_failed(db, analysis, "text_unavailable")
            return {"analysis_id": analysis_id, "status": "failed"}

        try:
            text = decrypt_text(analysis.encrypted_text)
        except DecryptionError:
            analysis_service.mark_failed(db, analysis, "text_undecryptable")
            return {"analysis_id": analysis_id, "status": "failed"}

        analysis_service.transition(analysis, AnalysisStatus.RUNNING)
        db.flush()

        try:
            provider = get_provider(settings)
            result = analyse(text, provider, settings)
        except InputRejected as exc:
            analysis_service.mark_failed(db, analysis, exc.code)
            return {"analysis_id": analysis_id, "status": "failed"}
        except SoftTimeLimitExceeded:
            analysis_service.mark_failed(db, analysis, "analysis_timeout")
            return {"analysis_id": analysis_id, "status": "failed"}
        except DetectorError as exc:
            # A model outage is transient; input problems are not.
            analysis_service.mark_failed(db, analysis, exc.code)
            logger.error(
                "analysis failed",
                extra={
                    "event": "task_failed",
                    "analysis_id": analysis_id,
                    "failure_code": exc.code,
                },
            )
            return {"analysis_id": analysis_id, "status": "failed"}

        analysis_service.apply_result(
            db, analysis, result, display_text=text if analysis.store_original_text else None
        )

        # The submission is retained only when the owner asked for it.
        if not analysis.store_original_text:
            analysis.encrypted_text = None
            db.add(analysis)

        logger.info(
            "analysis completed",
            extra={
                "event": "task_completed",
                "analysis_id": analysis_id,
                "word_count": result.word_count,
            },
        )
        return {"analysis_id": analysis_id, "status": "completed"}


@celery_app.task(name="originlens.retention_sweep")
def retention_sweep() -> dict[str, int]:
    """Remove expired guest results, stale sessions, and aged analyses."""
    settings = get_settings()
    with session_scope() as db:
        from app.auth.sessions import purge_expired

        guests = analysis_service.purge_expired_guest_analyses(db)
        aged = analysis_service.purge_expired_analyses(db, settings)
        sessions = purge_expired(db)

    logger.info(
        "retention sweep complete",
        extra={
            "event": "retention_sweep",
            "guest_analyses_removed": guests,
            "aged_analyses_removed": aged,
            "sessions_removed": sessions,
        },
    )
    return {
        "guest_analyses_removed": guests,
        "aged_analyses_removed": aged,
        "sessions_removed": sessions,
    }
