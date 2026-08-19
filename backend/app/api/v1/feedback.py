"""Feedback on a result.

Feedback is about the *result*, never a place to resubmit the document. The
comment is stored as given and escaped at render time; it is never interpolated
into HTML or a log line here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import DbDep, OptionalUserDep, enforce_rate_limit
from app.api.schemas import FeedbackRequest, FeedbackResponse
from app.core.errors import NotFound
from app.db.models import Feedback
from app.services import analysis as analysis_service

router = APIRouter(tags=["feedback"])


@router.post(
    "/analyses/{analysis_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_feedback(
    analysis_id: uuid.UUID,
    body: FeedbackRequest,
    request: Request,
    db: DbDep,
    user: OptionalUserDep,
    token: Annotated[str | None, Query(max_length=200)] = None,
) -> FeedbackResponse:
    """Record agreement or disagreement with a result."""
    enforce_rate_limit("feedback", request)

    analysis = None
    if user is not None:
        analysis = analysis_service.load_for_owner(db, analysis_id, user)
    if analysis is None and token:
        analysis = analysis_service.load_for_guest(db, analysis_id, token)
    if analysis is None:
        raise NotFound("That analysis was not found.")

    entry = Feedback(
        analysis_id=analysis.id,
        user_id=user.id if user else None,
        verdict=body.verdict,
        comment=body.comment,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return FeedbackResponse.model_validate(entry)
