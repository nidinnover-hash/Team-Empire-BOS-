import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.logs.audit import record_action
from app.models.approval import Approval
from app.models.employee import Employee
from app.models.user import User
from app.schemas.approval import (
    ApprovalDecision,
    ApprovalRead,
    ApprovalRequestCreate,
    ApprovalTimelineItem,
    ApprovalTimelineResponse,
)
from app.services import approval as approval_service
from app.services import clone_control, execution_engine

router = APIRouter(prefix="/approvals", tags=["Approvals"])
logger = logging.getLogger(__name__)
RISKY_APPROVAL_TYPES = {
    "send_message",
    "assign_task",
    "assign_leads",
    "change_crm_status",
    "spend_money",
    "spend",
}


async def _record_approval_feedback(
    db: AsyncSession,
    *,
    approval: Approval,
    outcome_score: float,
    actor_user_id: int,
    note: str,
) -> None:
    """Best-effort learning feedback record from approval outcomes."""
    requester = (
        await db.execute(
            select(User).where(
                User.id == approval.requested_by,
                User.organization_id == approval.organization_id,
            )
        )
    ).scalar_one_or_none()
    if requester is None:
        return
    employee = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == approval.organization_id,
                func.lower(Employee.email) == requester.email.lower(),
            )
        )
    ).scalar_one_or_none()
    if employee is None:
        return
    await clone_control.record_feedback(
        db,
        organization_id=approval.organization_id,
        employee_id=int(employee.id),
        source_type="approval",
        source_id=approval.id,
        outcome_score=max(0.0, min(1.0, float(outcome_score))),
        notes=note[:2000],
        created_by=actor_user_id,
    )


async def _record_feedback_telemetry_event(
    *,
    db: AsyncSession,
    actor: dict,
    approval: Approval,
    path: str,
    status: str,
    error_type: str | None = None,
) -> None:
    payload = {"path": path, "status": status}
    if error_type:
        payload["error_type"] = error_type
    try:
        await record_action(
            db=db,
            event_type="approval_feedback_recorded" if status == "ok" else "approval_feedback_failed",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="approval",
            entity_id=approval.id,
            payload_json=payload,
        )
    except (SQLAlchemyError, RuntimeError, ValueError, TypeError):
        logger.debug("approval feedback telemetry event failed", exc_info=True)


@router.post("/request", response_model=ApprovalRead, status_code=201)
async def request_approval(
    data: ApprovalRequestCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ApprovalRead:
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    approval = await approval_service.request_approval(db, actor["id"], data)
    await record_action(
        db,
        event_type="approval_requested",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="approval",
        entity_id=approval.id,
        payload_json={"approval_type": approval.approval_type, "request_id": get_current_request_id()},
    )
    return approval


@router.get("", response_model=list[ApprovalRead])
async def list_approvals(
    status: Literal["pending", "approved", "rejected"] | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[ApprovalRead]:
    rows = await approval_service.list_approvals(
        db,
        organization_id=actor["org_id"],
        status=status,
        limit=limit,
        offset=offset,
    )
    return [ApprovalRead.model_validate(row, from_attributes=True) for row in rows]


@router.get("/timeline", response_model=ApprovalTimelineResponse)
async def approval_timeline(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ApprovalTimelineResponse:
    items = await approval_service.list_approvals(
        db,
        organization_id=actor["org_id"],
        limit=limit,
        offset=offset,
    )
    timeline_items = [
        ApprovalTimelineItem(
            id=a.id,
            approval_type=a.approval_type,
            status=a.status,
            requested_by=a.requested_by,
            approved_by=a.approved_by,
            created_at=a.created_at,
            approved_at=a.approved_at,
            is_risky=a.approval_type in RISKY_APPROVAL_TYPES,
            requires_yes_execute=a.approval_type in RISKY_APPROVAL_TYPES,
        )
        for a in items
    ]

    counts_result = await db.execute(
        select(Approval.status, func.count(Approval.id))
        .where(Approval.organization_id == actor["org_id"])
        .group_by(Approval.status)
    )
    counts = {s: c for s, c in counts_result.all()}

    return ApprovalTimelineResponse(
        pending_count=int(counts.get("pending", 0)),
        approved_count=int(counts.get("approved", 0)),
        rejected_count=int(counts.get("rejected", 0)),
        items=timeline_items,
    )


@router.post("/{approval_id}/approve", response_model=ApprovalRead)
async def approve(
    approval_id: int,
    data: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ApprovalRead:
    should_execute = (data.note or "").strip().upper() == "YES EXECUTE"
    existing = await approval_service.get_approval(
        db,
        approval_id,
        organization_id=actor["org_id"],
    )
    if (
        existing is None
        or existing.organization_id != actor["org_id"]
        or existing.status != "pending"
    ):
        raise HTTPException(status_code=404, detail="Pending approval not found")
    if (
        existing.approval_type in RISKY_APPROVAL_TYPES
        and not should_execute
    ):
        raise HTTPException(
            status_code=400,
            detail="Risky approvals require note 'YES EXECUTE'",
        )
    approval = await approval_service.approve_approval(
        db,
        approval_id,
        actor["id"],
        organization_id=actor["org_id"],
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Pending approval not found")
    await record_action(
        db,
        event_type="approval_granted",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="approval",
        entity_id=approval.id,
        payload_json={"status": approval.status, "request_id": get_current_request_id()},
    )
    if should_execute:
        await execution_engine.execute_approval(
            db,
            approval=approval,
            actor_user_id=actor["id"],
            actor_org_id=actor["org_id"],
        )
    try:
        await _record_approval_feedback(
            db,
            approval=approval,
            outcome_score=1.0 if should_execute else 0.85,
            actor_user_id=int(actor["id"]),
            note=f"Approval {approval.approval_type} marked approved",
        )
        await _record_feedback_telemetry_event(
            db=db,
            actor=actor,
            approval=approval,
            path="approve",
            status="ok",
        )
    except (SQLAlchemyError, ValueError, TypeError) as exc:
        logger.warning("approval feedback write failed (approve path): %s", type(exc).__name__, exc_info=True)
        await _record_feedback_telemetry_event(
            db=db,
            actor=actor,
            approval=approval,
            path="approve",
            status="error",
            error_type=type(exc).__name__,
        )
    return approval


@router.post("/{approval_id}/reject", response_model=ApprovalRead)
async def reject(
    approval_id: int,
    _data: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ApprovalRead:
    existing = await approval_service.get_approval(
        db,
        approval_id,
        organization_id=actor["org_id"],
    )
    if (
        existing is None
        or existing.organization_id != actor["org_id"]
        or existing.status != "pending"
    ):
        raise HTTPException(status_code=404, detail="Pending approval not found")

    approval = await approval_service.reject_approval(
        db,
        approval_id,
        actor["id"],
        organization_id=actor["org_id"],
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Pending approval not found")
    await record_action(
        db,
        event_type="approval_rejected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="approval",
        entity_id=approval.id,
        payload_json={"status": approval.status, "request_id": get_current_request_id()},
    )
    try:
        await _record_approval_feedback(
            db,
            approval=approval,
            outcome_score=0.15,
            actor_user_id=int(actor["id"]),
            note=f"Approval {approval.approval_type} rejected",
        )
        await _record_feedback_telemetry_event(
            db=db,
            actor=actor,
            approval=approval,
            path="reject",
            status="ok",
        )
    except (SQLAlchemyError, ValueError, TypeError) as exc:
        logger.warning("approval feedback write failed (reject path): %s", type(exc).__name__, exc_info=True)
        await _record_feedback_telemetry_event(
            db=db,
            actor=actor,
            approval=approval,
            path="reject",
            status="error",
            error_type=type(exc).__name__,
        )
    return approval
