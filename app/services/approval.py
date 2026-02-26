from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select, update
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
    return cast(Approval | None, result.scalar_one_or_none())


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
    await db.commit()
    if result.rowcount == 0:
        return None
    return await get_approval(db, approval_id, organization_id=organization_id)


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
    await db.commit()
    if result.rowcount == 0:
        return None
    return await get_approval(db, approval_id, organization_id=organization_id)
