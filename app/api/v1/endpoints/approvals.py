from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.models.approval import Approval
from app.schemas.approval import (
    ApprovalDecision,
    ApprovalRead,
    ApprovalRequestCreate,
    ApprovalTimelineItem,
    ApprovalTimelineResponse,
)
from app.services import approval as approval_service
from app.services import execution_engine

router = APIRouter(prefix="/approvals", tags=["Approvals"])
RISKY_APPROVAL_TYPES = {
    "send_message",
    "assign_task",
    "assign_leads",
    "change_crm_status",
    "spend_money",
    "spend",
}


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
        payload_json={"approval_type": approval.approval_type},
    )
    return approval


@router.get("", response_model=list[ApprovalRead])
async def list_approvals(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[ApprovalRead]:
    return await approval_service.list_approvals(
        db,
        organization_id=actor["org_id"],
        status=status,
    )


@router.get("/timeline", response_model=ApprovalTimelineResponse)
async def approval_timeline(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ApprovalTimelineResponse:
    items = await approval_service.list_approvals(
        db,
        organization_id=actor["org_id"],
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
        for a in items[:limit]
    ]

    counts_result = await db.execute(
        select(Approval.status, func.count(Approval.id))
        .where(Approval.organization_id == actor["org_id"])
        .group_by(Approval.status)
    )
    counts = {status: count for status, count in counts_result.all()}

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
        payload_json={"status": approval.status},
    )
    if should_execute:
        await execution_engine.execute_approval(
            db,
            approval=approval,
            actor_user_id=actor["id"],
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
    if existing is None or existing.status != "pending":
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
        payload_json={"status": approval.status},
    )
    return approval
