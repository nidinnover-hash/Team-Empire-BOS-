"""Email drip campaign service."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drip_campaign import DripCampaign, DripStep, DripEnrollment


async def create_campaign(
    db: AsyncSession, *, organization_id: int, name: str,
    description: str | None = None, trigger_event: str | None = None,
    is_active: bool = False,
) -> DripCampaign:
    row = DripCampaign(
        organization_id=organization_id, name=name,
        description=description, trigger_event=trigger_event,
        is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_campaigns(db: AsyncSession, organization_id: int, *, is_active: bool | None = None) -> list[DripCampaign]:
    q = select(DripCampaign).where(DripCampaign.organization_id == organization_id)
    if is_active is not None:
        q = q.where(DripCampaign.is_active == is_active)
    q = q.order_by(DripCampaign.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_campaign(db: AsyncSession, campaign_id: int, organization_id: int) -> DripCampaign | None:
    q = select(DripCampaign).where(DripCampaign.id == campaign_id, DripCampaign.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_campaign(db: AsyncSession, campaign_id: int, organization_id: int, **kwargs) -> DripCampaign | None:
    row = await get_campaign(db, campaign_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_campaign(db: AsyncSession, campaign_id: int, organization_id: int) -> bool:
    row = await get_campaign(db, campaign_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def add_step(
    db: AsyncSession, *, organization_id: int, campaign_id: int,
    step_order: int = 0, delay_days: int = 0,
    subject: str = "", body: str = "",
) -> DripStep:
    step = DripStep(
        organization_id=organization_id, campaign_id=campaign_id,
        step_order=step_order, delay_days=delay_days,
        subject=subject, body=body,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def list_steps(db: AsyncSession, organization_id: int, campaign_id: int) -> list[DripStep]:
    q = select(DripStep).where(DripStep.organization_id == organization_id, DripStep.campaign_id == campaign_id).order_by(DripStep.step_order)
    return list((await db.execute(q)).scalars().all())


async def enroll(
    db: AsyncSession, *, organization_id: int, campaign_id: int, contact_id: int,
) -> DripEnrollment:
    row = DripEnrollment(
        organization_id=organization_id, campaign_id=campaign_id,
        contact_id=contact_id,
    )
    db.add(row)
    campaign = await get_campaign(db, campaign_id, organization_id)
    if campaign:
        campaign.total_enrolled += 1
    await db.commit()
    await db.refresh(row)
    return row


async def list_enrollments(
    db: AsyncSession, organization_id: int, campaign_id: int,
    *, status: str | None = None, limit: int = 100,
) -> list[DripEnrollment]:
    q = select(DripEnrollment).where(DripEnrollment.organization_id == organization_id, DripEnrollment.campaign_id == campaign_id)
    if status:
        q = q.where(DripEnrollment.status == status)
    q = q.order_by(DripEnrollment.enrolled_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def unsubscribe(db: AsyncSession, enrollment_id: int, organization_id: int) -> DripEnrollment | None:
    q = select(DripEnrollment).where(DripEnrollment.id == enrollment_id, DripEnrollment.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return None
    row.status = "unsubscribed"
    campaign = await get_campaign(db, row.campaign_id, organization_id)
    if campaign:
        campaign.total_unsubscribed += 1
    await db.commit()
    await db.refresh(row)
    return row
