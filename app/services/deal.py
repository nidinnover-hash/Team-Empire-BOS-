"""Deal service — CRUD and pipeline analytics for the Deal model."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import DEAL_STAGES, Deal

logger = logging.getLogger(__name__)

_UPDATE_FIELDS = {
    "contact_id", "title", "stage", "value", "probability",
    "expected_close_date", "description", "source", "lost_reason",
}


async def create_deal(
    db: AsyncSession, data: dict, organization_id: int, owner_user_id: int | None = None,
) -> Deal:
    deal = Deal(organization_id=organization_id, owner_user_id=owner_user_id, **data)
    db.add(deal)
    await db.commit()
    await db.refresh(deal)
    return deal


async def list_deals(
    db: AsyncSession, organization_id: int,
    *, contact_id: int | None = None, stage: str | None = None,
    limit: int = 100, offset: int = 0,
) -> list[Deal]:
    q = select(Deal).where(Deal.organization_id == organization_id)
    if contact_id is not None:
        q = q.where(Deal.contact_id == contact_id)
    if stage:
        q = q.where(Deal.stage == stage)
    q = q.order_by(Deal.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_deal(db: AsyncSession, deal_id: int, organization_id: int) -> Deal | None:
    result = await db.execute(
        select(Deal).where(Deal.id == deal_id, Deal.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def update_deal(
    db: AsyncSession, deal_id: int, organization_id: int, **kwargs,
) -> Deal | None:
    deal = await get_deal(db, deal_id, organization_id)
    if deal is None:
        return None

    for k, v in kwargs.items():
        if k in _UPDATE_FIELDS:
            setattr(deal, k, v)

    # Auto-set won_at/lost_at timestamps
    newly_won = kwargs.get("stage") == "won" and deal.won_at is None
    if newly_won:
        deal.won_at = datetime.now(UTC)
    if kwargs.get("stage") == "lost" and deal.lost_at is None:
        deal.lost_at = datetime.now(UTC)

    deal.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(deal)

    # Auto-create income entry when deal is won
    if newly_won and float(deal.value) > 0:
        try:
            await _create_income_for_won_deal(db, deal)
        except Exception:
            logger.warning("Failed to create finance entry for won deal %d", deal.id, exc_info=True)

    return deal


async def _create_income_for_won_deal(db: AsyncSession, deal: Deal) -> None:
    """Bridge: auto-create a finance income entry when a deal is marked won."""
    from app.models.finance import FinanceEntry

    entry = FinanceEntry(
        organization_id=deal.organization_id,
        type="income",
        amount=float(deal.value),
        category="sales",
        description=f"Deal won: {deal.title}",
        entry_date=datetime.now(UTC).date(),
    )
    db.add(entry)
    await db.commit()
    logger.info("Auto-created income entry for won deal %d ($%.2f)", deal.id, float(deal.value))


async def delete_deal(db: AsyncSession, deal_id: int, organization_id: int) -> bool:
    deal = await get_deal(db, deal_id, organization_id)
    if deal is None:
        return False
    await db.delete(deal)
    await db.commit()
    return True


async def get_deal_summary(db: AsyncSession, organization_id: int) -> dict:
    """Pipeline analytics for deals."""
    total_q = await db.execute(
        select(
            func.count(Deal.id),
            func.coalesce(func.sum(Deal.value), 0.0),
        ).where(Deal.organization_id == organization_id)
    )
    row = total_q.one()
    total_deals = row[0] or 0
    total_value = float(row[1] or 0.0)

    won_q = await db.execute(
        select(
            func.count(Deal.id),
            func.coalesce(func.sum(Deal.value), 0.0),
        ).where(Deal.organization_id == organization_id, Deal.stage == "won")
    )
    won_row = won_q.one()
    won_value = float(won_row[1] or 0.0)

    lost_q = await db.execute(
        select(func.count(Deal.id))
        .where(Deal.organization_id == organization_id, Deal.stage == "lost")
    )
    lost_count = lost_q.scalar() or 0

    closed = (won_row[0] or 0) + lost_count
    win_rate = round(((won_row[0] or 0) / max(closed, 1)) * 100, 1)

    # Per-stage breakdown
    stage_q = await db.execute(
        select(
            Deal.stage,
            func.count(Deal.id),
            func.coalesce(func.sum(Deal.value), 0.0),
            func.coalesce(func.avg(Deal.value), 0.0),
            func.coalesce(func.avg(Deal.probability), 0.0),
        ).where(Deal.organization_id == organization_id)
        .group_by(Deal.stage)
    )
    pipeline = []
    for r in stage_q.all():
        pipeline.append({
            "stage": r[0],
            "count": r[1],
            "total_value": round(float(r[2]), 2),
            "avg_value": round(float(r[3]), 2),
            "avg_probability": round(float(r[4]), 1),
        })

    return {
        "total_deals": total_deals,
        "total_value": round(total_value, 2),
        "won_value": round(won_value, 2),
        "lost_count": lost_count,
        "win_rate": win_rate,
        "avg_deal_size": round(total_value / max(total_deals, 1), 2),
        "pipeline": sorted(pipeline, key=lambda x: DEAL_STAGES.index(x["stage"]) if x["stage"] in DEAL_STAGES else 99),
    }


async def get_deal_forecast(
    db: AsyncSession, organization_id: int, months: int = 6,
) -> dict:
    """Revenue forecast based on open deals, their probability, and expected close dates."""
    result = await db.execute(
        select(Deal).where(
            Deal.organization_id == organization_id,
            Deal.stage.notin_(["won", "lost"]),
        )
    )
    open_deals = list(result.scalars().all())

    today = date.today()
    monthly: dict[str, dict] = {}

    for i in range(months):
        month_date = today.replace(day=1) + timedelta(days=32 * i)
        key = month_date.strftime("%Y-%m")
        monthly[key] = {"month": key, "weighted": 0.0, "unweighted": 0.0, "deal_count": 0}

    # No-close-date deals get spread across all months
    no_date_deals = [d for d in open_deals if d.expected_close_date is None]
    dated_deals = [d for d in open_deals if d.expected_close_date is not None]

    for deal in dated_deals:
        key = deal.expected_close_date.strftime("%Y-%m")
        if key in monthly:
            val = float(deal.value)
            prob = (deal.probability or 0) / 100.0
            monthly[key]["weighted"] += round(val * prob, 2)
            monthly[key]["unweighted"] += round(val, 2)
            monthly[key]["deal_count"] += 1

    # Spread undated deals evenly
    if no_date_deals and monthly:
        per_month = len(monthly)
        for deal in no_date_deals:
            val = float(deal.value) / per_month
            prob = (deal.probability or 0) / 100.0
            for m in monthly.values():
                m["weighted"] += round(val * prob, 2)
                m["unweighted"] += round(val, 2)
                m["deal_count"] += 1

    forecast = sorted(monthly.values(), key=lambda x: x["month"])
    total_weighted = round(sum(m["weighted"] for m in forecast), 2)
    total_unweighted = round(sum(m["unweighted"] for m in forecast), 2)

    return {
        "months": forecast,
        "total_weighted": total_weighted,
        "total_unweighted": total_unweighted,
        "open_deals": len(open_deals),
    }
