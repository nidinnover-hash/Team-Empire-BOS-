"""Sales forecast scenario endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import forecast_scenario as svc

router = APIRouter(prefix="/forecast-scenarios", tags=["forecast-scenarios"])


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    period: str
    scenario_type: str
    total_pipeline: float
    weighted_value: float
    expected_close: float
    notes: str | None = None
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ScenarioCreate(BaseModel):
    name: str
    period: str
    scenario_type: str = "likely"
    total_pipeline: float = 0
    weighted_value: float = 0
    expected_close: float = 0
    assumptions: dict | None = None
    notes: str | None = None


class ScenarioUpdate(BaseModel):
    name: str | None = None
    scenario_type: str | None = None
    total_pipeline: float | None = None
    weighted_value: float | None = None
    expected_close: float | None = None
    assumptions: dict | None = None
    notes: str | None = None


@router.post("", response_model=ScenarioOut, status_code=201)
async def create_scenario(
    body: ScenarioCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_scenario(db, organization_id=actor["org_id"], created_by_user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[ScenarioOut])
async def list_scenarios(
    period: str | None = None, scenario_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_scenarios(db, actor["org_id"], period=period, scenario_type=scenario_type)


@router.get("/compare/{period}")
async def compare_scenarios(
    period: str, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.compare_scenarios(db, actor["org_id"], period)


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_scenario(db, scenario_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Scenario not found")
    return row


@router.put("/{scenario_id}", response_model=ScenarioOut)
async def update_scenario(
    scenario_id: int, body: ScenarioUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_scenario(db, scenario_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Scenario not found")
    return row


@router.delete("/{scenario_id}", status_code=204)
async def delete_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_scenario(db, scenario_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Scenario not found")
