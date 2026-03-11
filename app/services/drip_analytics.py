"""Drip campaign analytics service."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drip_analytics import DripStepEvent


async def record_event(db: AsyncSession, *, organization_id: int, **kw) -> DripStepEvent:
    row = DripStepEvent(organization_id=organization_id, **kw)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_events(db: AsyncSession, org_id: int, *, campaign_id: int | None = None, step_id: int | None = None, event_type: str | None = None, limit: int = 100) -> list[DripStepEvent]:
    q = select(DripStepEvent).where(DripStepEvent.organization_id == org_id)
    if campaign_id:
        q = q.where(DripStepEvent.campaign_id == campaign_id)
    if step_id:
        q = q.where(DripStepEvent.step_id == step_id)
    if event_type:
        q = q.where(DripStepEvent.event_type == event_type)
    q = q.order_by(DripStepEvent.created_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_step_stats(db: AsyncSession, org_id: int, campaign_id: int) -> list[dict]:
    q = (
        select(
            DripStepEvent.step_id,
            DripStepEvent.event_type,
            func.count(DripStepEvent.id).label("cnt"),
        )
        .where(DripStepEvent.organization_id == org_id, DripStepEvent.campaign_id == campaign_id)
        .group_by(DripStepEvent.step_id, DripStepEvent.event_type)
    )
    rows = (await db.execute(q)).all()
    result: dict[int, dict] = {}
    for r in rows:
        sid = r.step_id
        if sid not in result:
            result[sid] = {"step_id": sid, "sent": 0, "opened": 0, "clicked": 0, "bounced": 0, "unsubscribed": 0}
        result[sid][r.event_type] = r.cnt
    return list(result.values())


async def get_campaign_summary(db: AsyncSession, org_id: int, campaign_id: int) -> dict:
    q = (
        select(DripStepEvent.event_type, func.count(DripStepEvent.id).label("cnt"))
        .where(DripStepEvent.organization_id == org_id, DripStepEvent.campaign_id == campaign_id)
        .group_by(DripStepEvent.event_type)
    )
    rows = (await db.execute(q)).all()
    summary = {"sent": 0, "opened": 0, "clicked": 0, "bounced": 0, "unsubscribed": 0}
    for r in rows:
        summary[r.event_type] = r.cnt
    sent = summary["sent"] or 1
    summary["open_rate"] = round(summary["opened"] / sent * 100, 1)
    summary["click_rate"] = round(summary["clicked"] / sent * 100, 1)
    summary["bounce_rate"] = round(summary["bounced"] / sent * 100, 1)
    return summary
