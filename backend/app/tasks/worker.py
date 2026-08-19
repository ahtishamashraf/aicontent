"""Celery application.

Concurrency is deliberately constrained. A transformer checkpoint is loaded
once per worker *process*, so every additional process is another full copy of
the weights in RAM. Prefetch is pinned to one so a single worker cannot reserve
a queue of expensive jobs it will not start for minutes.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "originlens",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.analysis_tasks"],
)

celery_app.conf.update(
    # --- Safety -------------------------------------------------------------
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    # --- Bounded work --------------------------------------------------------
    # Hard kill well after the soft limit so a task can fail cleanly first.
    task_soft_time_limit=240,
    task_time_limit=300,
    # --- Inference concurrency ----------------------------------------------
    # One job in flight per process, and one reserved: model memory is the
    # constraint, not CPU scheduling.
    worker_prefetch_multiplier=1,
    worker_concurrency=1,
    worker_max_tasks_per_child=200,
    # --- Serialisation -------------------------------------------------------
    # JSON only. Pickle would make a queue write into remote code execution.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # --- Results -------------------------------------------------------------
    # Results carry only status codes; the database is the record.
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)


@worker_process_init.connect
def _init_process(**_: Any) -> None:
    """Prepare a freshly forked worker process.

    Engines and Redis clients must not be inherited across a fork: the parent's
    sockets would be shared by every child. The model provider is loaded lazily
    on first use so that a worker starts (and reports health) promptly.
    """
    from app.core.ratelimit import reset_redis
    from app.db.session import reset_engine
    from detection.registry import reset_provider

    configure_logging(settings.log_level)
    reset_engine()
    reset_redis()
    reset_provider()
    logger.info(
        "worker process ready",
        extra={"event": "worker_init", "detector_backend": settings.detector_backend},
    )


@worker_process_shutdown.connect
def _shutdown_process(**_: Any) -> None:
    from app.core.ratelimit import reset_redis
    from app.db.session import reset_engine

    reset_engine()
    reset_redis()
    logger.info("worker process stopping", extra={"event": "worker_shutdown"})
