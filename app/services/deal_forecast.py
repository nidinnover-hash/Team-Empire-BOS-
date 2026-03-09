"""Deal pipeline forecasting — weighted pipeline, win rates, stage conversion."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import DEAL_STAGES, Deal


async def get_pipeline_forecast(
    db: AsyncSession, organization_id: int,
) -> dict:
    """Weighted pipeline forecast by stage."""
    result = await db.execute(
        select(Deal).where(
            Deal.organization_id == organization_id,
            Deal.stage.notin_(("won", "lost")),
        )
    )
    deals = list(result.scalars().all())

    stages: dict[str, dict] = {}
    total_weighted = 0.0
    total_unweighted = 0.0

    for deal in deals:
        s = deal.stage
        if s not in stages:
            stages[s] = {"count": 0, "total_value": 0.0, "weighted_value": 0.0}
        stages[s]["count"] += 1
        val = float(deal.value or 0)
        prob = float(deal.probability or 0) / 100.0
        stages[s]["total_value"] += val
        stages[s]["weighted_value"] += val * prob
        total_weighted += val * prob
        total_unweighted += val

    stage_breakdown = [
        {"stage": s, **data} for s, data in stages.items()
    ]
    stage_breakdown.sort(key=lambda x: DEAL_STAGES.index(x["stage"]) if x["stage"] in DEAL_STAGES else 99)

    return {
        "total_pipeline_value": round(total_unweighted, 2),
        "total_weighted_value": round(total_weighted, 2),
        "active_deals": len(deals),
        "stages": stage_breakdown,
    }


async def get_win_rate_trends(
    db: AsyncSession, organization_id: int, months: int = 6,
) -> dict:
    """Win rate by month for the last N months."""
    today = date.today()
    start = today.replace(day=1) - timedelta(days=months * 30)

    won_rows = await db.execute(
        select(
            func.strftime("%Y-%m", Deal.won_at),
            func.count(Deal.id),
            func.sum(Deal.value),
        ).where(
            Deal.organization_id == organization_id,
            Deal.stage == "won",
            Deal.won_at >= datetime(start.year, start.month, start.day, tzinfo=UTC),
        ).group_by(func.strftime("%Y-%m", Deal.won_at))
    )
    won_map = {r[0]: {"count": r[1], "value": float(r[2] or 0)} for r in won_rows}

    lost_rows = await db.execute(
        select(
            func.strftime("%Y-%m", Deal.lost_at),
            func.count(Deal.id),
        ).where(
            Deal.organization_id == organization_id,
            Deal.stage == "lost",
            Deal.lost_at >= datetime(start.year, start.month, start.day, tzinfo=UTC),
        ).group_by(func.strftime("%Y-%m", Deal.lost_at))
    )
    lost_map = {r[0]: r[1] for r in lost_rows}

    all_months = sorted(set(list(won_map.keys()) + list(lost_map.keys())))
    trends = []
    for m in all_months:
        won_count = won_map.get(m, {}).get("count", 0) or 0
        lost_count = lost_map.get(m, 0) or 0
        total = won_count + lost_count
        win_rate = round(won_count / total * 100, 1) if total > 0 else 0
        trends.append({
            "month": m,
            "won": won_count,
            "lost": lost_count,
            "win_rate": win_rate,
            "won_value": round(won_map.get(m, {}).get("value", 0), 2),
        })

    return {"months": months, "trends": trends}
