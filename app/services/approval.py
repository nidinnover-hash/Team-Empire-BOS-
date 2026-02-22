from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.schemas.approval import ApprovalRequestCreate


async def request_approval(
    db: AsyncSession, requested_by: int, data: ApprovalRequestCreate
) -> Approval:
    approval = Approval(
        organization_id=data.organization_id,
        requested_by=requested_by,
        approval_type=data.approval_type,
        payload_json=data.payload_json,
        status="pending",
    )
    db.add(approval)
    await db.commit()
    await db.refresh(approval)
    return approval


async def get_approval(
    db: AsyncSession,
    approval_id: int,
    organization_id: int | None = None,
) -> Approval | None:
    query = select(Approval).where(Approval.id == approval_id)
    if organization_id is not None:
        query = query.where(Approval.organization_id == organization_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_approvals(
    db: AsyncSession, organization_id: int, status: str | None = None
) -> list[Approval]:
    query = select(Approval).order_by(Approval.created_at.desc())
    query = query.where(Approval.organization_id == organization_id)
    if status is not None:
        query = query.where(Approval.status == status)
    result = await db.execute(query)
    return list(result.scalars().all())


async def approve_approval(
    db: AsyncSession,
    approval_id: int,
    approver_id: int,
    organization_id: int,
) -> Approval | None:
    approval = await get_approval(db, approval_id, organization_id=organization_id)
    if approval is None or approval.status != "pending":
        return None
    approval.status = "approved"
    approval.approved_by = approver_id
    approval.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(approval)
    return approval


async def reject_approval(
    db: AsyncSession,
    approval_id: int,
    approver_id: int,
    organization_id: int,
) -> Approval | None:
    approval = await get_approval(db, approval_id, organization_id=organization_id)
    if approval is None or approval.status != "pending":
        return None
    approval.status = "rejected"
    approval.approved_by = approver_id
    approval.approved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(approval)
    return approval
