import logging
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
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
from app.schemas.approval_pattern import ApprovalPatternRead, ApprovalPatternUpdate
from app.services import alert as alert_service
from app.services import approval as approval_service
from app.services import approval_pattern as pattern_service
from app.services import autonomy_policy, clone_control, execution_engine
from app.services import execution as execution_service
from app.services import organization as org_service
from app.services import webhook as webhook_service

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
NON_FATAL_SIDE_EFFECT_ERRORS = (SQLAlchemyError, RuntimeError, ValueError, TypeError)


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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> ApprovalRead:
    if data.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Cross-organization access denied")
    org = await org_service.get_organization_by_id(db, int(actor["org_id"]))
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if idempotency_key:
        existing = (
            await db.execute(
                select(Approval).where(
                    Approval.organization_id == int(actor["org_id"]),
                    Approval.request_idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            same_shape = (
                existing.approval_type == data.approval_type
                and (existing.payload_json or {}) == (data.payload_json or {})
            )
            if not same_shape:
                raise HTTPException(status_code=409, detail="Idempotency key reused with different approval payload")
            return existing
    approval = await approval_service.request_approval(db, actor["id"], data)
    if idempotency_key:
        approval.request_idempotency_key = idempotency_key
        await db.commit()
        await db.refresh(approval)
    await record_action(
        db,
        event_type="approval_requested",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="approval",
        entity_id=approval.id,
        payload_json={"approval_type": approval.approval_type, "request_id": get_current_request_id()},
    )
    # Check confidence pattern — auto-approve if eligible
    try:
        should_auto, confidence = await pattern_service.should_auto_approve(
            db, int(actor["org_id"]), data.approval_type, data.payload_json
        )
        approval.confidence_score = confidence if confidence > 0 else None
        if should_auto and data.approval_type not in RISKY_APPROVAL_TYPES:
            can_auto_approve, denial_reason = await autonomy_policy.can_auto_approve(db, org=org)
            if can_auto_approve:
                from datetime import UTC, datetime
                approval.status = "approved"
                approval.approved_by = int(actor["id"])
                approval.approved_at = datetime.now(UTC)
                approval.auto_approved_at = datetime.now(UTC)
                await db.commit()
                await db.refresh(approval)
                await record_action(
                    db,
                    event_type="approval_auto_approved",
                    actor_user_id=actor["id"],
                    organization_id=actor["org_id"],
                    entity_type="approval",
                    entity_id=approval.id,
                    payload_json={"confidence_score": confidence, "approval_type": approval.approval_type},
                )
            else:
                await db.commit()
                await db.refresh(approval)
                logger.info("auto-approve denied by autonomy policy: %s", denial_reason)
        else:
            await db.commit()
            await db.refresh(approval)
    except NON_FATAL_SIDE_EFFECT_ERRORS as exc:
        logger.warning("approval pattern check failed: %s", type(exc).__name__, exc_info=True)
    # Fire outgoing webhook
    try:
        await webhook_service.trigger_org_webhooks(
            db,
            organization_id=int(actor["org_id"]),
            event="approval.created",
            payload={
                "approval_id": approval.id,
                "approval_type": approval.approval_type,
                "status": approval.status,
                "requested_by": approval.requested_by,
            },
        )
    except NON_FATAL_SIDE_EFFECT_ERRORS as exc:
        logger.warning("webhook: approval.created failed: %s", type(exc).__name__)
    # Alert for risky types still pending
    if data.approval_type in RISKY_APPROVAL_TYPES and approval.status == "pending":
        try:
            await alert_service.send_pending_alert(
                db,
                org_id=int(actor["org_id"]),
                entity_type="approval",
                entity_id=approval.id,
                title=f"Risky approval pending: {approval.approval_type}",
                detail=(
                    f"Approval #{approval.id} of type '{approval.approval_type}' "
                    "requires CEO/ADMIN sign-off with note 'YES EXECUTE'."
                ),
            )
        except NON_FATAL_SIDE_EFFECT_ERRORS as exc:
            logger.warning("alert: approval pending failed: %s", type(exc).__name__)
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ApprovalRead:
    should_execute = (data.note or "").strip().upper() == "YES EXECUTE"
    if should_execute and not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required for YES EXECUTE")
    if should_execute and idempotency_key:
        existing_exec = await execution_service.get_execution_by_idempotency_key(
            db,
            organization_id=int(actor["org_id"]),
            execute_idempotency_key=idempotency_key,
        )
        if existing_exec is not None:
            replay = await approval_service.get_approval(
                db,
                existing_exec.approval_id,
                organization_id=int(actor["org_id"]),
            )
            if replay is not None:
                return replay
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
    org = await org_service.get_organization_by_id(db, int(actor["org_id"]))
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if should_execute:
        can_execute, denial_reason = await autonomy_policy.can_execute_post_approval(db, org=org)
        if not can_execute:
            raise HTTPException(status_code=409, detail=denial_reason)
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
            execute_idempotency_key=idempotency_key,
        )
    # Record pattern decision
    try:
        p = await pattern_service.get_or_create(
            db, int(actor["org_id"]), approval.approval_type, approval.payload_json
        )
        await pattern_service.record_decision(db, p.id, approved=True, decided_by_id=int(actor["id"]))
        await db.commit()
    except NON_FATAL_SIDE_EFFECT_ERRORS as exc:
        logger.warning("pattern record failed (approve): %s", type(exc).__name__)
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
    try:
        await webhook_service.trigger_org_webhooks(
            db,
            organization_id=int(actor["org_id"]),
            event="approval.approved",
            payload={
                "approval_id": approval.id,
                "approval_type": approval.approval_type,
                "approved_by": approval.approved_by,
            },
        )
    except NON_FATAL_SIDE_EFFECT_ERRORS as exc:
        logger.warning("webhook: approval.approved failed: %s", type(exc).__name__)
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
    # Record pattern decision
    try:
        p = await pattern_service.get_or_create(
            db, int(actor["org_id"]), approval.approval_type, approval.payload_json
        )
        await pattern_service.record_decision(db, p.id, approved=False, decided_by_id=int(actor["id"]))
        await db.commit()
    except NON_FATAL_SIDE_EFFECT_ERRORS as exc:
        logger.warning("pattern record failed (reject): %s", type(exc).__name__)
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
    try:
        await webhook_service.trigger_org_webhooks(
            db,
            organization_id=int(actor["org_id"]),
            event="approval.rejected",
            payload={
                "approval_id": approval.id,
                "approval_type": approval.approval_type,
            },
        )
    except NON_FATAL_SIDE_EFFECT_ERRORS as exc:
        logger.warning("webhook: approval.rejected failed: %s", type(exc).__name__)
    return approval


# ---------------------------------------------------------------------------
# Approval pattern management
# ---------------------------------------------------------------------------

@router.get("/approval-patterns", response_model=list[ApprovalPatternRead])
async def list_approval_patterns(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[ApprovalPatternRead]:
    """List all learned approval patterns with confidence scores."""
    patterns = await pattern_service.list_patterns(db, organization_id=int(actor["org_id"]))
    result = []
    for p in patterns:
        read = ApprovalPatternRead.model_validate(p, from_attributes=True)
        read.reject_count = read.rejected_count
        read.confidence_score = pattern_service.compute_confidence(p)
        result.append(read)
    return result


@router.patch("/approval-patterns/{pattern_id}", response_model=ApprovalPatternRead)
async def update_approval_pattern(
    pattern_id: int,
    data: ApprovalPatternUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> ApprovalPatternRead:
    """Enable/disable auto-approve or adjust threshold for a pattern."""
    pattern = await pattern_service.update_pattern(
        db, pattern_id, int(actor["org_id"]),
        data.is_auto_approve_enabled, data.auto_approve_threshold,
    )
    if pattern is None:
        raise HTTPException(status_code=404, detail="Pattern not found")
    read = ApprovalPatternRead.model_validate(pattern, from_attributes=True)
    read.reject_count = read.rejected_count
    read.confidence_score = pattern_service.compute_confidence(pattern)
    return read


@router.delete("/approval-patterns/{pattern_id}", status_code=204)
async def delete_approval_pattern(
    pattern_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO")),
) -> None:
    """Reset (delete) an approval pattern to clear its learned history."""
    deleted = await pattern_service.delete_pattern(db, pattern_id, int(actor["org_id"]))
    if not deleted:
        raise HTTPException(status_code=404, detail="Pattern not found")
    await record_action(
        db, event_type="approval_pattern_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="approval_pattern", entity_id=pattern_id,
    )
