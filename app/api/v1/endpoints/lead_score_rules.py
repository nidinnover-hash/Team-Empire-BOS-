"""Lead scoring rules engine endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import lead_score_rule as svc

router = APIRouter(prefix="/lead-score-rules", tags=["lead-score-rules"])


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    rule_type: str
    field_name: str | None = None
    operator: str | None = None
    value: str | None = None
    score_delta: int
    weight: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RuleCreate(BaseModel):
    name: str
    rule_type: str = "field"
    field_name: str | None = None
    operator: str | None = None
    value: str | None = None
    score_delta: int = 0
    weight: float = 1.0
    is_active: bool = True
    conditions: dict | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    rule_type: str | None = None
    field_name: str | None = None
    operator: str | None = None
    value: str | None = None
    score_delta: int | None = None
    weight: float | None = None
    is_active: bool | None = None
    conditions: dict | None = None


class EvaluateBody(BaseModel):
    contact_data: dict


@router.post("", response_model=RuleOut, status_code=201)
async def create_rule(
    body: RuleCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_rule(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[RuleOut])
async def list_rules(
    rule_type: str | None = None, is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_rules(db, actor["org_id"], rule_type=rule_type, is_active=is_active)


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(
    rule_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_rule(db, rule_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Rule not found")
    return row


@router.put("/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: int, body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_rule(db, rule_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Rule not found")
    return row


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_rule(db, rule_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Rule not found")


@router.post("/evaluate")
async def evaluate_rules(
    body: EvaluateBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.evaluate_rules(db, actor["org_id"], body.contact_data)
