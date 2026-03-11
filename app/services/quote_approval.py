"""Quote approval service."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quote_approval import QuoteApproval


async def request_approval(db: AsyncSession, *, organization_id: int, **kw) -> QuoteApproval:
    row = QuoteApproval(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_approvals(db: AsyncSession, org_id: int, *, quote_id: int | None = None, status: str | None = None) -> list[QuoteApproval]:
    q = select(QuoteApproval).where(QuoteApproval.organization_id == org_id)
    if quote_id:
        q = q.where(QuoteApproval.quote_id == quote_id)
    if status:
        q = q.where(QuoteApproval.status == status)
    q = q.order_by(QuoteApproval.level, QuoteApproval.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def decide(db: AsyncSession, approval_id: int, org_id: int, status: str, reason: str | None = None) -> QuoteApproval | None:
    row = (await db.execute(select(QuoteApproval).where(
        QuoteApproval.id == approval_id,
        QuoteApproval.organization_id == org_id,
        QuoteApproval.status == "pending",  # Only pending approvals can be decided
    ))).scalar_one_or_none()
    if not row:
        return None
    row.status = status
    row.reason = reason
    row.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row


async def get_pending_count(db: AsyncSession, org_id: int, approver_user_id: int | None = None) -> dict:
    q = select(func.count(QuoteApproval.id)).where(QuoteApproval.organization_id == org_id, QuoteApproval.status == "pending")
    if approver_user_id:
        q = q.where(QuoteApproval.approver_user_id == approver_user_id)
    total = (await db.execute(q)).scalar() or 0
    return {"pending_count": total}
