"""Contact score decay — automatic score reduction for inactive contacts."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import score_decay as sd_service

router = APIRouter(prefix="/score-decay", tags=["Score Decay"])


class DecayRuleCreate(BaseModel):
    name: str = Field(..., max_length=200)
    inactive_days: int = Field(30, ge=1)
    decay_points: int = Field(5, ge=1)
    min_score: int = Field(0, ge=0)
    frequency: str = Field("daily", pattern=r"^(daily|weekly)$")


class DecayRuleUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    inactive_days: int | None = Field(None, ge=1)
    decay_points: int | None = Field(None, ge=1)
    min_score: int | None = Field(None, ge=0)
    is_active: bool | None = None


class DecayRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    inactive_days: int
    decay_points: int
    min_score: int
    frequency: str
    is_active: bool
    last_run_at: datetime | None = None
    contacts_affected: int
    created_at: datetime | None = None


@router.get("", response_model=list[DecayRuleRead])
async def list_decay_rules(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[DecayRuleRead]:
    items = await sd_service.list_rules(db, organization_id=actor["org_id"], active_only=active_only)
    return [DecayRuleRead.model_validate(r, from_attributes=True) for r in items]


@router.post("", response_model=DecayRuleRead, status_code=201)
async def create_decay_rule(
    data: DecayRuleCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DecayRuleRead:
    rule = await sd_service.create_rule(db, organization_id=actor["org_id"], **data.model_dump())
    return DecayRuleRead.model_validate(rule, from_attributes=True)


@router.patch("/{rule_id}", response_model=DecayRuleRead)
async def update_decay_rule(
    rule_id: int,
    data: DecayRuleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DecayRuleRead:
    rule = await sd_service.update_rule(
        db, rule_id=rule_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return DecayRuleRead.model_validate(rule, from_attributes=True)


@router.delete("/{rule_id}", status_code=204)
async def delete_decay_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await sd_service.delete_rule(db, rule_id=rule_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")


@router.get("/{rule_id}/simulate")
async def simulate_decay(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    result = await sd_service.simulate_decay(db, rule_id=rule_id, organization_id=actor["org_id"])
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
