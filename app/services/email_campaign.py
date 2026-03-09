"""Email campaign service — create, manage, and execute drip campaigns."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_campaign import CampaignEnrollment, CampaignStep, EmailCampaign

logger = logging.getLogger(__name__)


async def create_campaign(
    db: AsyncSession,
    organization_id: int,
    name: str,
    *,
    description: str | None = None,
    created_by_user_id: int | None = None,
) -> EmailCampaign:
    campaign = EmailCampaign(
        organization_id=organization_id,
        name=name,
        description=description,
        created_by_user_id=created_by_user_id,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def list_campaigns(
    db: AsyncSession,
    organization_id: int,
    status: str | None = None,
) -> list[EmailCampaign]:
    q = select(EmailCampaign).where(EmailCampaign.organization_id == organization_id)
    if status:
        q = q.where(EmailCampaign.status == status)
    q = q.order_by(EmailCampaign.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_campaign(
    db: AsyncSession,
    organization_id: int,
    campaign_id: int,
) -> EmailCampaign | None:
    result = await db.execute(
        select(EmailCampaign).where(
            EmailCampaign.id == campaign_id,
            EmailCampaign.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_campaign_status(
    db: AsyncSession,
    organization_id: int,
    campaign_id: int,
    status: str,
) -> EmailCampaign | None:
    campaign = await get_campaign(db, organization_id, campaign_id)
    if campaign is None:
        return None
    campaign.status = status
    campaign.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def add_step(
    db: AsyncSession,
    campaign_id: int,
    subject: str,
    body_template: str,
    *,
    step_order: int = 1,
    delay_hours: int = 24,
) -> CampaignStep:
    step = CampaignStep(
        campaign_id=campaign_id,
        step_order=step_order,
        subject=subject,
        body_template=body_template,
        delay_hours=delay_hours,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def list_steps(
    db: AsyncSession,
    campaign_id: int,
) -> list[CampaignStep]:
    result = await db.execute(
        select(CampaignStep).where(CampaignStep.campaign_id == campaign_id)
        .order_by(CampaignStep.step_order)
    )
    return list(result.scalars().all())


async def enroll_contact(
    db: AsyncSession,
    campaign_id: int,
    contact_id: int,
) -> CampaignEnrollment:
    # Check if already enrolled
    existing = await db.execute(
        select(CampaignEnrollment).where(
            CampaignEnrollment.campaign_id == campaign_id,
            CampaignEnrollment.contact_id == contact_id,
            CampaignEnrollment.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        return existing.scalar_one_or_none()

    # Get first step delay
    steps = await list_steps(db, campaign_id)
    first_delay = steps[0].delay_hours if steps else 24

    enrollment = CampaignEnrollment(
        campaign_id=campaign_id,
        contact_id=contact_id,
        current_step=0,
        next_send_at=datetime.now(UTC) + timedelta(hours=first_delay),
    )
    db.add(enrollment)
    await db.commit()
    await db.refresh(enrollment)
    return enrollment


async def list_enrollments(
    db: AsyncSession,
    campaign_id: int,
    status: str | None = None,
) -> list[CampaignEnrollment]:
    q = select(CampaignEnrollment).where(CampaignEnrollment.campaign_id == campaign_id)
    if status:
        q = q.where(CampaignEnrollment.status == status)
    return list((await db.execute(q.order_by(CampaignEnrollment.enrolled_at.desc()))).scalars().all())


async def get_campaign_summary(
    db: AsyncSession,
    organization_id: int,
    campaign_id: int,
) -> dict | None:
    campaign = await get_campaign(db, organization_id, campaign_id)
    if campaign is None:
        return None

    steps = await list_steps(db, campaign_id)
    enrollments = await list_enrollments(db, campaign_id)
    active = [e for e in enrollments if e.status == "active"]
    completed = [e for e in enrollments if e.status == "completed"]

    return {
        "id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "step_count": len(steps),
        "total_enrolled": len(enrollments),
        "active_enrolled": len(active),
        "completed": len(completed),
    }
