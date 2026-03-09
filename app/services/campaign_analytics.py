"""Campaign analytics service — track and query campaign performance."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign_analytics import CampaignEvent


async def record_event(
    db: AsyncSession,
    organization_id: int,
    campaign_id: int,
    event_type: str,
    step_id: int | None = None,
    enrollment_id: int | None = None,
    contact_id: int | None = None,
    variant: str | None = None,
    metadata_json: str | None = None,
) -> CampaignEvent:
    event = CampaignEvent(
        organization_id=organization_id,
        campaign_id=campaign_id,
        step_id=step_id,
        enrollment_id=enrollment_id,
        contact_id=contact_id,
        event_type=event_type,
        variant=variant,
        metadata_json=metadata_json,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_campaign_analytics(
    db: AsyncSession,
    organization_id: int,
    campaign_id: int,
) -> dict:
    """Aggregate analytics for a campaign: totals by event type and per step."""
    # Overall totals
    totals_rows = await db.execute(
        select(CampaignEvent.event_type, func.count(CampaignEvent.id))
        .where(
            CampaignEvent.organization_id == organization_id,
            CampaignEvent.campaign_id == campaign_id,
        )
        .group_by(CampaignEvent.event_type)
    )
    totals = {r[0]: r[1] for r in totals_rows}

    sent = totals.get("sent", 0)
    opened = totals.get("opened", 0)
    clicked = totals.get("clicked", 0)

    open_rate = round(opened / sent * 100, 1) if sent > 0 else 0
    click_rate = round(clicked / sent * 100, 1) if sent > 0 else 0

    # Per-step breakdown
    step_rows = await db.execute(
        select(
            CampaignEvent.step_id,
            CampaignEvent.event_type,
            func.count(CampaignEvent.id),
        )
        .where(
            CampaignEvent.organization_id == organization_id,
            CampaignEvent.campaign_id == campaign_id,
            CampaignEvent.step_id.isnot(None),
        )
        .group_by(CampaignEvent.step_id, CampaignEvent.event_type)
    )
    steps: dict[int, dict] = {}
    for row in step_rows:
        sid, etype, cnt = row[0], row[1], row[2]
        if sid not in steps:
            steps[sid] = {}
        steps[sid][etype] = cnt

    step_analytics = []
    for sid, counts in sorted(steps.items()):
        s_sent = counts.get("sent", 0)
        s_opened = counts.get("opened", 0)
        s_clicked = counts.get("clicked", 0)
        step_analytics.append({
            "step_id": sid,
            "sent": s_sent,
            "opened": s_opened,
            "clicked": s_clicked,
            "open_rate": round(s_opened / s_sent * 100, 1) if s_sent > 0 else 0,
            "click_rate": round(s_clicked / s_sent * 100, 1) if s_sent > 0 else 0,
        })

    # A/B variant breakdown
    variant_rows = await db.execute(
        select(
            CampaignEvent.variant,
            CampaignEvent.event_type,
            func.count(CampaignEvent.id),
        )
        .where(
            CampaignEvent.organization_id == organization_id,
            CampaignEvent.campaign_id == campaign_id,
            CampaignEvent.variant.isnot(None),
        )
        .group_by(CampaignEvent.variant, CampaignEvent.event_type)
    )
    variants: dict[str, dict] = {}
    for row in variant_rows:
        v, etype, cnt = row[0], row[1], row[2]
        if v not in variants:
            variants[v] = {}
        variants[v][etype] = cnt

    variant_analytics = []
    for v, counts in sorted(variants.items()):
        v_sent = counts.get("sent", 0)
        v_opened = counts.get("opened", 0)
        v_clicked = counts.get("clicked", 0)
        variant_analytics.append({
            "variant": v,
            "sent": v_sent,
            "opened": v_opened,
            "clicked": v_clicked,
            "open_rate": round(v_opened / v_sent * 100, 1) if v_sent > 0 else 0,
            "click_rate": round(v_clicked / v_sent * 100, 1) if v_sent > 0 else 0,
        })

    return {
        "campaign_id": campaign_id,
        "totals": totals,
        "sent": sent,
        "opened": opened,
        "clicked": clicked,
        "bounced": totals.get("bounced", 0),
        "unsubscribed": totals.get("unsubscribed", 0),
        "open_rate": open_rate,
        "click_rate": click_rate,
        "steps": step_analytics,
        "variants": variant_analytics,
    }
