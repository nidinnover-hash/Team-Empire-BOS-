import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import PIPELINE_STAGES, Contact
from app.schemas.contact import ContactCreate, ContactUpdate, PipelineSummary

logger = logging.getLogger(__name__)


_UPDATE_FIELDS = {
    "name", "email", "phone", "company", "role", "relationship", "notes",
    "pipeline_stage", "lead_score", "lead_source", "deal_value",
    "expected_close_date", "last_contacted_at", "next_follow_up_at", "tags",
}


async def create_contact(
    db: AsyncSession, data: ContactCreate, organization_id: int
) -> Contact:
    contact = Contact(**data.model_dump(), organization_id=organization_id)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    logger.info("contact created id=%d org=%d", contact.id, organization_id)
    return contact


async def list_contacts(
    db: AsyncSession,
    organization_id: int,
    limit: int = 100,
    offset: int = 0,
    *,
    pipeline_stage: str | None = None,
    lead_score_min: int | None = None,
    lead_score_max: int | None = None,
    relationship: str | None = None,
    search: str | None = None,
) -> list[Contact]:
    query = select(Contact).where(Contact.organization_id == organization_id)
    if pipeline_stage:
        query = query.where(Contact.pipeline_stage == pipeline_stage)
    if lead_score_min is not None:
        query = query.where(Contact.lead_score >= lead_score_min)
    if lead_score_max is not None:
        query = query.where(Contact.lead_score <= lead_score_max)
    if relationship:
        query = query.where(Contact.relationship == relationship)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Contact.name.ilike(pattern)
            | Contact.email.ilike(pattern)
            | Contact.company.ilike(pattern)
        )
    result = await db.execute(
        query.order_by(Contact.name).offset(offset).limit(limit)
    )
    return list(result.scalars().all())


async def get_contact(
    db: AsyncSession, contact_id: int, organization_id: int,
) -> Contact | None:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def update_contact(
    db: AsyncSession, contact_id: int, data: ContactUpdate, organization_id: int,
) -> Contact | None:
    contact = await get_contact(db, contact_id, organization_id)
    if contact is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in _UPDATE_FIELDS:
            setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    logger.info("contact updated id=%d org=%d", contact_id, organization_id)
    return contact


async def delete_contact(
    db: AsyncSession, contact_id: int, organization_id: int,
) -> bool:
    contact = await get_contact(db, contact_id, organization_id)
    if contact is None:
        return False
    await db.delete(contact)
    await db.commit()
    logger.info("contact deleted id=%d org=%d", contact_id, organization_id)
    return True


async def get_follow_up_due(
    db: AsyncSession, organization_id: int, limit: int = 50,
) -> list[Contact]:
    """Contacts whose next_follow_up_at is in the past or today."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(Contact)
        .where(
            Contact.organization_id == organization_id,
            Contact.next_follow_up_at.isnot(None),
            Contact.next_follow_up_at <= now,
        )
        .order_by(Contact.next_follow_up_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_pipeline_summary(
    db: AsyncSession, organization_id: int,
) -> list[PipelineSummary]:
    """Aggregate count + total deal value per pipeline stage."""
    result = await db.execute(
        select(
            Contact.pipeline_stage,
            func.count(Contact.id),
            func.coalesce(func.sum(Contact.deal_value), 0.0),
        )
        .where(Contact.organization_id == organization_id)
        .group_by(Contact.pipeline_stage)
    )
    rows = result.all()
    stage_map = {row[0]: (row[1], row[2]) for row in rows}
    return [
        PipelineSummary(
            stage=stage,
            count=stage_map.get(stage, (0, 0.0))[0],
            total_deal_value=float(stage_map.get(stage, (0, 0.0))[1]),
        )
        for stage in PIPELINE_STAGES
    ]
