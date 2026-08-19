"""Analysis submission, polling, retrieval, listing, and deletion.

Ownership is enforced in the query itself rather than by comparing fields after
a lookup, so an IDOR attempt returns the same 404 as a genuinely missing row and
cannot be distinguished from it.
"""

from __future__ import annotations

import math
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Body, File, Query, Request, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    OptionalUserDep,
    SettingsDep,
    enforce_rate_limit,
)
from app.api.schemas import (
    AnalysisListResponse,
    AnalysisResponse,
    AnalysisStatusResponse,
    AnalysisSummary,
    AnalyzeTextRequest,
    CountsResponse,
    IntegrityWarningResponse,
    MessageResponse,
    SegmentResponse,
)
from app.core.crypto import DecryptionError, decrypt_text
from app.core.errors import (
    AnalysisUnavailable,
    DocumentRejected,
    NotFound,
    PayloadTooLarge,
    ValidationFailed,
)
from app.db.models import Analysis, AnalysisSource, AnalysisStatus, User
from app.services import analysis as analysis_service
from app.services import audit
from app.services.documents import (
    DocumentRejectedError,
    extract_document,
    safe_display_filename,
)
from detection.engines.base import DetectorError
from detection.pipeline import InputRejected, analyse
from detection.registry import get_provider

router = APIRouter(prefix="/analyses", tags=["analyses"])

#: Upload streaming chunk size. Bounded reads stop a hostile client from
#: forcing an unbounded allocation before the size check runs.
_CHUNK_BYTES = 64 * 1024


def _segment_payloads(analysis: Analysis, *, include_text: bool) -> list[SegmentResponse]:
    payloads: list[SegmentResponse] = []
    for segment in analysis.segments:
        text: str | None = None
        if include_text and segment.encrypted_text:
            try:
                text = decrypt_text(segment.encrypted_text)
            except DecryptionError:
                text = None
        payloads.append(
            SegmentResponse(
                id=f"p-{segment.index:03d}",
                index=segment.index,
                text=text,
                word_count=segment.word_count,
                character_count=segment.character_count,
                public_score=segment.public_score,
                raw_model_score=segment.raw_model_score,
                label=segment.label,
                too_short=segment.too_short,
                grouped_with_context=segment.grouped_with_context,
            )
        )
    return payloads


def _to_response(
    analysis: Analysis, *, guest_token: str | None = None, include_text: bool = True
) -> AnalysisResponse:
    warnings = [
        IntegrityWarningResponse(code=code, message=code.replace("_", " ").capitalize())
        for code in (analysis.integrity_warnings or [])
    ]
    return AnalysisResponse(
        id=analysis.id,
        status=analysis.status.value,
        source=analysis.source.value,
        source_filename=analysis.source_filename,
        created_at=analysis.created_at,
        completed_at=analysis.completed_at,
        label=analysis.label,
        public_score=analysis.public_score,
        raw_model_score=analysis.raw_model_score,
        reliability=analysis.reliability.value if analysis.reliability else None,
        reliability_reasons=analysis.reliability_reasons or [],
        counts=CountsResponse(
            words=analysis.word_count,
            characters=analysis.character_count,
            paragraphs=analysis.paragraph_count,
        ),
        detected_language=analysis.detected_language,
        language_confidence=analysis.language_confidence,
        window_stability=analysis.window_stability,
        segments=_segment_payloads(analysis, include_text=include_text),
        integrity_warnings=warnings,
        diagnostics=analysis.diagnostics,
        model_metadata=analysis.model_metadata,
        calibration_version=analysis.calibration_version,
        detector_version=analysis.detector_version,
        failure_code=analysis.failure_code,
        guest_token=guest_token,
        stored_original_text=analysis.store_original_text,
        disclaimers=analysis_service.disclaimers(),
    )


def _run_analysis(
    db: DbDep,
    settings: SettingsDep,
    analysis: Analysis,
    text: str,
) -> None:
    """Execute the pipeline and persist the outcome.

    Runs inline so a submission is complete when the request returns. The same
    service functions back the Celery path, so both routes share one state
    machine.
    """
    analysis_service.transition(analysis, AnalysisStatus.RUNNING)
    db.flush()

    try:
        provider = get_provider(settings)
    except DetectorError as exc:
        analysis_service.mark_failed(db, analysis, exc.code)
        db.commit()
        raise AnalysisUnavailable() from exc

    try:
        result = analyse(text, provider, settings)
    except InputRejected as exc:
        analysis_service.mark_failed(db, analysis, exc.code)
        db.commit()
        raise ValidationFailed(exc.message) from exc
    except DetectorError as exc:
        analysis_service.mark_failed(db, analysis, exc.code)
        db.commit()
        raise AnalysisUnavailable() from exc

    analysis_service.apply_result(db, analysis, result, display_text=text)
    db.commit()
    db.refresh(analysis)


@router.post("/text", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def submit_text(
    body: Annotated[AnalyzeTextRequest, Body()],
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    user: OptionalUserDep,
) -> AnalysisResponse:
    """Submit text for analysis, as a guest or an authenticated user."""
    enforce_rate_limit("user_analysis" if user else "guest_analysis", request)

    if len(body.text) > settings.max_characters:
        raise PayloadTooLarge(
            f"The submission exceeds the {settings.max_characters:,}-character limit."
        )

    analysis, guest_token = analysis_service.create_analysis(
        db,
        settings,
        user=user,
        source=AnalysisSource.TEXT,
        store_original_text=body.store_original_text,
    )
    _run_analysis(db, settings, analysis, body.text)

    return _to_response(analysis, guest_token=guest_token)


@router.post("/document", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
async def submit_document(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    user: OptionalUserDep,
    file: Annotated[UploadFile, File()],
    store_original_text: Annotated[bool, Query()] = False,
) -> AnalysisResponse:
    """Upload a .txt, .pdf, or .docx file for analysis."""
    enforce_rate_limit("upload", request)

    filename = safe_display_filename(file.filename or "document")

    # Read with a hard ceiling so an oversized upload cannot be buffered whole.
    payload = bytearray()
    while chunk := await file.read(_CHUNK_BYTES):
        payload.extend(chunk)
        if len(payload) > settings.max_upload_bytes:
            raise PayloadTooLarge(
                f"The file exceeds the {settings.max_upload_bytes // (1024 * 1024)} "
                "MiB upload limit."
            )

    try:
        extraction = extract_document(filename, bytes(payload), settings.max_upload_bytes)
    except DocumentRejectedError as exc:
        raise DocumentRejected(exc.message) from exc
    finally:
        # No temporary file is written, but close the spooled handle promptly.
        await file.close()

    analysis, guest_token = analysis_service.create_analysis(
        db,
        settings,
        user=user,
        source=AnalysisSource.DOCUMENT,
        source_filename=filename,
        store_original_text=store_original_text,
    )
    _run_analysis(db, settings, analysis, extraction.text)

    return _to_response(analysis, guest_token=guest_token)


@router.get("/{analysis_id}/status", response_model=AnalysisStatusResponse)
def analysis_status(
    analysis_id: uuid.UUID,
    db: DbDep,
    user: OptionalUserDep,
    token: Annotated[str | None, Query(max_length=200)] = None,
) -> AnalysisStatusResponse:
    """Poll job state. Requires ownership or the guest token."""
    analysis = _authorise(db, analysis_id, user, token)
    return AnalysisStatusResponse(
        id=analysis.id, status=analysis.status.value, failure_code=analysis.failure_code
    )


def _authorise(db: DbDep, analysis_id: uuid.UUID, user: User | None, token: str | None) -> Analysis:
    """Resolve an analysis for this caller, or raise a uniform 404."""
    if user is not None:
        owned = analysis_service.load_for_owner(db, analysis_id, user)
        if owned is not None:
            return owned
    if token:
        guest = analysis_service.load_for_guest(db, analysis_id, token)
        if guest is not None:
            return guest
    # Same response for "does not exist" and "not yours": the difference is
    # exactly the information an IDOR probe is looking for.
    raise NotFound("That analysis was not found.")


@router.get("/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(
    analysis_id: uuid.UUID,
    db: DbDep,
    user: OptionalUserDep,
    token: Annotated[str | None, Query(max_length=200)] = None,
) -> AnalysisResponse:
    """Fetch a full result by ownership or guest token."""
    analysis = _authorise(db, analysis_id, user, token)
    return _to_response(analysis)


@router.get("", response_model=AnalysisListResponse)
def list_analyses(
    user: CurrentUserDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[
        Literal["queued", "running", "completed", "failed"] | None, Query(alias="status")
    ] = None,
    source: Annotated[Literal["text", "document"] | None, Query()] = None,
) -> AnalysisListResponse:
    """List the caller's own analyses."""
    conditions = [Analysis.user_id == user.id]
    if status_filter:
        conditions.append(Analysis.status == AnalysisStatus(status_filter))
    if source:
        conditions.append(Analysis.source == AnalysisSource(source))

    total = int(
        db.execute(select(func.count()).select_from(Analysis).where(*conditions)).scalar_one()
    )
    rows = (
        db.execute(
            select(Analysis)
            .where(*conditions)
            .order_by(Analysis.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return AnalysisListResponse(
        items=[
            AnalysisSummary(
                id=row.id,
                status=row.status.value,
                source=row.source.value,
                source_filename=row.source_filename,
                created_at=row.created_at,
                label=row.label,
                public_score=row.public_score,
                reliability=row.reliability.value if row.reliability else None,
                word_count=row.word_count,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


@router.delete("/{analysis_id}", response_model=MessageResponse)
def delete_analysis(analysis_id: uuid.UUID, user: CurrentUserDep, db: DbDep) -> MessageResponse:
    """Delete one of the caller's analyses, including any stored text."""
    analysis = analysis_service.load_for_owner(db, analysis_id, user)
    if analysis is None:
        raise NotFound("That analysis was not found.")

    analysis_service.delete_analysis(db, analysis)
    audit.record(
        db,
        "analysis.deleted",
        actor_user_id=user.id,
        target_type="analysis",
        target_id=str(analysis_id),
    )
    db.commit()
    return MessageResponse(message="The analysis was deleted.")


@router.delete("", response_model=MessageResponse)
def delete_all_analyses(user: CurrentUserDep, db: DbDep) -> MessageResponse:
    """Delete every analysis owned by the caller."""
    removed = analysis_service.delete_all_for_user(db, user)
    audit.record(
        db,
        "analysis.deleted_all",
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        context={"removed": removed},
    )
    db.commit()
    return MessageResponse(message=f"{removed} analyses were deleted.")
