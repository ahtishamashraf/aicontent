"""Administrator routes.

Every route depends on ``AdminDep``, which re-checks the role server-side on
each request. A frontend guard is a convenience, never the control.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from app.api.deps import AdminDep, DbDep, SettingsDep, enforce_rate_limit
from app.api.schemas import (
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserSummary,
    AuditLogEntry,
    AuditLogListResponse,
    MessageResponse,
    ModelHealthResponse,
    SuspendUserRequest,
    SystemSettingResponse,
    SystemSettingUpdate,
)
from app.auth.sessions import revoke_all_for_user
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.models import (
    Analysis,
    AnalysisStatus,
    AuditLog,
    Feedback,
    SystemSetting,
    User,
    UserStatus,
)
from app.services import audit
from detection.registry import provider_status

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    admin: AdminDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    search: Annotated[str | None, Query(max_length=320)] = None,
) -> AdminUserListResponse:
    """List accounts. ``search`` is bound as a parameter, never interpolated."""
    conditions = []
    if search:
        conditions.append(User.email.ilike(f"%{search.strip().lower()}%"))

    total = int(db.execute(select(func.count()).select_from(User).where(*conditions)).scalar_one())
    rows = (
        db.execute(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return AdminUserListResponse(
        items=[AdminUserSummary.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


@router.post("/users/{user_id}/suspend", response_model=MessageResponse)
def suspend_user(
    user_id: uuid.UUID,
    body: SuspendUserRequest,
    request: Request,
    admin: AdminDep,
    db: DbDep,
) -> MessageResponse:
    """Suspend an account and revoke its sessions immediately."""
    enforce_rate_limit("admin_mutation", request)

    target = db.get(User, user_id)
    if target is None:
        raise NotFound("That account was not found.")
    if target.id == admin.id:
        raise Conflict("You cannot suspend your own account.")
    if target.status == UserStatus.SUSPENDED:
        raise Conflict("That account is already suspended.")

    target.status = UserStatus.SUSPENDED
    target.suspended_at = datetime.now(UTC)
    target.suspension_reason = body.reason
    db.add(target)

    revoked = revoke_all_for_user(db, target.id)
    audit.record(
        db,
        "admin.user_suspended",
        actor_user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
        context={"sessions_revoked": revoked},
    )
    db.commit()
    return MessageResponse(message="The account was suspended.")


@router.post("/users/{user_id}/reactivate", response_model=MessageResponse)
def reactivate_user(
    user_id: uuid.UUID, request: Request, admin: AdminDep, db: DbDep
) -> MessageResponse:
    """Return a suspended account to active."""
    enforce_rate_limit("admin_mutation", request)

    target = db.get(User, user_id)
    if target is None:
        raise NotFound("That account was not found.")
    if target.status != UserStatus.SUSPENDED:
        raise Conflict("That account is not suspended.")

    target.status = UserStatus.ACTIVE if target.email_verified_at else UserStatus.PENDING
    target.suspended_at = None
    target.suspension_reason = None
    db.add(target)
    audit.record(
        db,
        "admin.user_reactivated",
        actor_user_id=admin.id,
        target_type="user",
        target_id=str(target.id),
    )
    db.commit()
    return MessageResponse(message="The account was reactivated.")


@router.get("/stats", response_model=AdminStatsResponse)
def statistics(admin: AdminDep, db: DbDep) -> AdminStatsResponse:
    """Aggregate counts only. No submitted content is reachable from here."""

    def count(model: Any, *conditions: Any) -> int:
        return int(
            db.execute(select(func.count()).select_from(model).where(*conditions)).scalar_one()
        )

    since = datetime.now(UTC) - timedelta(hours=24)
    return AdminStatsResponse(
        users_total=count(User),
        users_active=count(User, User.status == UserStatus.ACTIVE),
        users_suspended=count(User, User.status == UserStatus.SUSPENDED),
        analyses_total=count(Analysis),
        analyses_completed=count(Analysis, Analysis.status == AnalysisStatus.COMPLETED),
        analyses_failed=count(Analysis, Analysis.status == AnalysisStatus.FAILED),
        analyses_last_24h=count(Analysis, Analysis.created_at >= since),
        feedback_total=count(Feedback),
    )


@router.get("/feedback")
def list_feedback(
    admin: AdminDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    """List feedback. Only the reviewer's comment is shown, never the document."""
    total = int(db.execute(select(func.count()).select_from(Feedback)).scalar_one())
    rows = (
        db.execute(
            select(Feedback)
            .order_by(Feedback.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "analysis_id": str(row.analysis_id),
                "verdict": row.verdict,
                "comment": row.comment,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
    }


@router.get("/settings", response_model=list[SystemSettingResponse])
def list_settings(admin: AdminDep, db: DbDep) -> list[SystemSettingResponse]:
    rows = db.execute(select(SystemSetting).order_by(SystemSetting.key)).scalars().all()
    return [
        SystemSettingResponse(
            key=row.key,
            value=row.value.get("value"),
            value_type=row.value_type,
            description=row.description,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.put("/settings/{key}", response_model=SystemSettingResponse)
def update_setting(
    key: str,
    body: SystemSettingUpdate,
    request: Request,
    admin: AdminDep,
    db: DbDep,
) -> SystemSettingResponse:
    """Update a typed setting, rejecting a value of the wrong type."""
    enforce_rate_limit("admin_mutation", request)

    setting = db.get(SystemSetting, key)
    if setting is None:
        raise NotFound("That setting was not found.")

    permitted: dict[str, tuple[type, ...]] = {
        "int": (int,),
        "float": (int, float),
        "bool": (bool,),
        "str": (str,),
    }
    expected = permitted.get(setting.value_type)
    # bool subclasses int, so a numeric setting must reject True explicitly.
    if expected is not None and (
        not isinstance(body.value, expected)
        or (setting.value_type in {"int", "float"} and isinstance(body.value, bool))
    ):
        raise ValidationFailed(f"This setting expects a {setting.value_type} value.")

    setting.value = {"value": body.value}
    setting.updated_by = admin.id
    db.add(setting)
    audit.record(
        db,
        "admin.setting_updated",
        actor_user_id=admin.id,
        target_type="setting",
        target_id=key,
        context={"key": key},
    )
    db.commit()
    db.refresh(setting)
    return SystemSettingResponse(
        key=setting.key,
        value=setting.value.get("value"),
        value_type=setting.value_type,
        description=setting.description,
        updated_at=setting.updated_at,
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    admin: AdminDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    action: Annotated[str | None, Query(max_length=80)] = None,
) -> AuditLogListResponse:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)

    total = int(
        db.execute(select(func.count()).select_from(AuditLog).where(*conditions)).scalar_one()
    )
    rows = (
        db.execute(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    return AuditLogListResponse(
        items=[AuditLogEntry.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/health/model", response_model=ModelHealthResponse)
def admin_model_health(admin: AdminDep, settings: SettingsDep) -> ModelHealthResponse:
    """Detailed model health, including load errors."""
    return ModelHealthResponse(**provider_status(settings))
