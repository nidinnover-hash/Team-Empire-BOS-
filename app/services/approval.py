from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.platform.signals import (
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    APPROVAL_REQUESTED,
    SignalCategory,
    SignalEnvelope,
    publish_signal,
)
from app.schemas.approval import ApprovalRequestCreate
from app.services.notification import create_notification


async def _publish_approval_signal(
    signal_type: str,
    approval: Approval,
    *,
    actor_user_id: int | None,
    db: AsyncSession | None = None,
) -> None:
    """Publish a best-effort approval lifecycle signal."""
    try:
        await publish_signal(
            SignalEnvelope(
                topic=signal_type,
                category=SignalCategory.DECISION,
                organization_id=approval.organization_id,
                actor_user_id=actor_user_id,
                source="approval.service",
                entity_type="approval",
                entity_id=str(approval.id),
                payload={
                    "approval_id": approval.id,
                    "approval_type": approval.approval_type,
                    "status": approval.status,
                    "requested_by": approval.requested_by,
                    "approved_by": approval.approved_by,
                    "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
                    "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
                },
            ),
            db=db,
        )
    except Exception:
        # Approval completion must not fail because signal fanout failed.
        return


async def request_approval(
    db: AsyncSession, requested_by: int, data: ApprovalRequestCreate
) -> Approval:
    from app.core.config import settings
    from app.models.approval import _DEFAULT_EXPIRY_HOURS
    sla_hours = max(1, int(getattr(settings, "APPROVAL_SLA_HOURS", _DEFAULT_EXPIRY_HOURS)))
    approval = Approval(
        organization_id=data.organization_id,
        requested_by=requested_by,
        approval_type=data.approval_type,
        payload_json=data.payload_json,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=sla_hours),
    )
    db.add(approval)
    await db.flush()
    await create_notification(
        db,
        organization_id=data.organization_id,
        type="approval_created",
        severity="info",
        title=f"New Approval: {data.approval_type}",
        message="Approval request awaiting decision.",
        source="approval",
        entity_type="approval",
        entity_id=approval.id,
    )
    await db.commit()
    await db.refresh(approval)
    await _publish_approval_signal(
        APPROVAL_REQUESTED,
        approval,
        actor_user_id=requested_by,
        db=db,
    )
    return approval


async def get_approval(
    db: AsyncSession,
    approval_id: int,
    organization_id: int,
) -> Approval | None:
    query = select(Approval).where(
        Approval.id == approval_id,
        Approval.organization_id == organization_id,
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_approvals(
    db: AsyncSession,
    organization_id: int,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Approval]:
    query = select(Approval).order_by(Approval.created_at.desc())
    query = query.where(Approval.organization_id == organization_id)
    if status is not None:
        query = query.where(Approval.status == status)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def approve_approval(
    db: AsyncSession,
    approval_id: int,
    approver_id: int,
    organization_id: int,
) -> Approval | None:
    # Atomic UPDATE WHERE status = 'pending' prevents two concurrent approvers
    result = await db.execute(
        update(Approval)
        .where(
            Approval.id == approval_id,
            Approval.organization_id == organization_id,
            Approval.status == "pending",
        )
        .values(
            status="approved",
            approved_by=approver_id,
            approved_at=datetime.now(UTC),
        )
    )
    if result.rowcount == 0:
        await db.rollback()
        return None
    await db.flush()
    approved = await get_approval(db, approval_id, organization_id=organization_id)
    if approved:
        await create_notification(
            db,
            organization_id=organization_id,
            type="approval_approved",
            severity="info",
            title=f"Approved: {approved.approval_type}",
            message="Approval granted. Execution may follow.",
            source="approval",
            entity_type="approval",
            entity_id=approval_id,
            user_id=approved.requested_by,
        )
    await db.commit()
    if approved:
        await _publish_approval_signal(
            APPROVAL_APPROVED,
            approved,
            actor_user_id=approver_id,
            db=db,
        )
    return approved


async def reject_approval(
    db: AsyncSession,
    approval_id: int,
    approver_id: int,
    organization_id: int,
) -> Approval | None:
    # Atomic UPDATE WHERE status = 'pending' prevents race conditions
    result = await db.execute(
        update(Approval)
        .where(
            Approval.id == approval_id,
            Approval.organization_id == organization_id,
            Approval.status == "pending",
        )
        .values(
            status="rejected",
            approved_by=approver_id,
            approved_at=datetime.now(UTC),
        )
    )
    if result.rowcount == 0:
        await db.rollback()
        return None
    await db.flush()
    rejected = await get_approval(db, approval_id, organization_id=organization_id)
    if rejected:
        await create_notification(
            db,
            organization_id=organization_id,
            type="approval_rejected",
            severity="warning",
            title=f"Rejected: {rejected.approval_type}",
            message="Approval request has been rejected.",
            source="approval",
            entity_type="approval",
            entity_id=approval_id,
            user_id=rejected.requested_by,
        )
    await db.commit()
    if rejected:
        await _publish_approval_signal(
            APPROVAL_REJECTED,
            rejected,
            actor_user_id=approver_id,
            db=db,
        )
    return rejected
