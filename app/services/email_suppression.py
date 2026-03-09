"""Email suppression service."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_suppression import EmailSuppression


async def add_suppression(
    db: AsyncSession, *, organization_id: int, email_or_domain: str,
    suppression_type: str, reason: str | None = None,
    source: str = "manual",
) -> EmailSuppression:
    row = EmailSuppression(
        organization_id=organization_id, email_or_domain=email_or_domain.lower(),
        suppression_type=suppression_type, reason=reason, source=source,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_suppressions(
    db: AsyncSession, organization_id: int, *,
    suppression_type: str | None = None, limit: int = 100,
) -> list[EmailSuppression]:
    q = select(EmailSuppression).where(EmailSuppression.organization_id == organization_id)
    if suppression_type:
        q = q.where(EmailSuppression.suppression_type == suppression_type)
    q = q.order_by(EmailSuppression.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def check_suppressed(db: AsyncSession, organization_id: int, email: str) -> bool:
    email_lower = email.lower()
    domain = email_lower.split("@")[-1] if "@" in email_lower else email_lower
    q = select(func.count(EmailSuppression.id)).where(
        EmailSuppression.organization_id == organization_id,
        EmailSuppression.email_or_domain.in_([email_lower, domain]),
    )
    count = (await db.execute(q)).scalar() or 0
    return count > 0


async def remove_suppression(db: AsyncSession, suppression_id: int, organization_id: int) -> bool:
    q = select(EmailSuppression).where(EmailSuppression.id == suppression_id, EmailSuppression.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def get_stats(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(EmailSuppression.suppression_type, func.count(EmailSuppression.id))
        .where(EmailSuppression.organization_id == organization_id)
        .group_by(EmailSuppression.suppression_type)
    )).all()
    return {t: c for t, c in rows}
