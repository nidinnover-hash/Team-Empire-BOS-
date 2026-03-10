"""Sales forecast scenario service."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.forecast_scenario import ForecastScenario


async def create_scenario(
    db: AsyncSession, *, organization_id: int, name: str,
    period: str, scenario_type: str = "likely",
    total_pipeline: float = 0, weighted_value: float = 0,
    expected_close: float = 0, assumptions: dict | None = None,
    notes: str | None = None, created_by_user_id: int | None = None,
) -> ForecastScenario:
    row = ForecastScenario(
        organization_id=organization_id, name=name, period=period,
        scenario_type=scenario_type, total_pipeline=total_pipeline,
        weighted_value=weighted_value, expected_close=expected_close,
        assumptions_json=json.dumps(assumptions or {}),
        notes=notes, created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_scenarios(
    db: AsyncSession, organization_id: int, *,
    period: str | None = None, scenario_type: str | None = None,
) -> list[ForecastScenario]:
    q = select(ForecastScenario).where(ForecastScenario.organization_id == organization_id)
    if period:
        q = q.where(ForecastScenario.period == period)
    if scenario_type:
        q = q.where(ForecastScenario.scenario_type == scenario_type)
    q = q.order_by(ForecastScenario.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_scenario(db: AsyncSession, scenario_id: int, organization_id: int) -> ForecastScenario | None:
    q = select(ForecastScenario).where(ForecastScenario.id == scenario_id, ForecastScenario.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_scenario(db: AsyncSession, scenario_id: int, organization_id: int, **kwargs) -> ForecastScenario | None:
    row = await get_scenario(db, scenario_id, organization_id)
    if not row:
        return None
    if "assumptions" in kwargs:
        kwargs["assumptions_json"] = json.dumps(kwargs.pop("assumptions") or {})
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_scenario(db: AsyncSession, scenario_id: int, organization_id: int) -> bool:
    row = await get_scenario(db, scenario_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def compare_scenarios(db: AsyncSession, organization_id: int, period: str) -> dict:
    scenarios = await list_scenarios(db, organization_id, period=period)
    result = {}
    for s in scenarios:
        result[s.scenario_type] = {
            "id": s.id, "name": s.name,
            "total_pipeline": float(s.total_pipeline),
            "weighted_value": float(s.weighted_value),
            "expected_close": float(s.expected_close),
        }
    return result
