"""Competitor tracking service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competitor import Competitor, DealCompetitor


async def create_competitor(
    db: AsyncSession, *, organization_id: int, name: str,
    website: str | None = None, strengths: str | None = None,
    weaknesses: str | None = None, notes: str | None = None,
) -> Competitor:
    row = Competitor(
        organization_id=organization_id, name=name, website=website,
        strengths=strengths, weaknesses=weaknesses, notes=notes,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_competitors(db: AsyncSession, organization_id: int) -> list[Competitor]:
    q = select(Competitor).where(Competitor.organization_id == organization_id).order_by(Competitor.name)
    return list((await db.execute(q)).scalars().all())


async def get_competitor(db: AsyncSession, competitor_id: int, organization_id: int) -> Competitor | None:
    q = select(Competitor).where(Competitor.id == competitor_id, Competitor.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_competitor(db: AsyncSession, competitor_id: int, organization_id: int, **kwargs) -> Competitor | None:
    row = await get_competitor(db, competitor_id, organization_id)
    if not row:
        return None
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_competitor(db: AsyncSession, competitor_id: int, organization_id: int) -> bool:
    row = await get_competitor(db, competitor_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def link_to_deal(
    db: AsyncSession, *, organization_id: int, deal_id: int,
    competitor_id: int, threat_level: str = "medium",
    win_loss_reason: str | None = None,
) -> DealCompetitor:
    row = DealCompetitor(
        organization_id=organization_id, deal_id=deal_id,
        competitor_id=competitor_id, threat_level=threat_level,
        win_loss_reason=win_loss_reason,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_deal_competitors(db: AsyncSession, organization_id: int, deal_id: int) -> list[DealCompetitor]:
    q = (
        select(DealCompetitor)
        .where(DealCompetitor.organization_id == organization_id, DealCompetitor.deal_id == deal_id)
    )
    return list((await db.execute(q)).scalars().all())


async def get_win_loss_stats(db: AsyncSession, organization_id: int) -> dict:
    rows = (await db.execute(
        select(DealCompetitor.threat_level, func.count(DealCompetitor.id))
        .where(DealCompetitor.organization_id == organization_id)
        .group_by(DealCompetitor.threat_level)
    )).all()
    return {level: count for level, count in rows}
