"""Contact deduplication rules endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import dedup_rule as svc

router = APIRouter(prefix="/dedup-rules", tags=["dedup-rules"])


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    merge_strategy: str
    confidence_threshold: float
    auto_merge: bool
    is_active: bool
    total_matches: int
    total_merges: int
    created_at: datetime
    updated_at: datetime


class RuleCreate(BaseModel):
    name: str
    match_fields: list[str] | None = None
    merge_strategy: str = "keep_newest"
    confidence_threshold: float = 0.8
    auto_merge: bool = False
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: str | None = None
    match_fields: list[str] | None = None
    merge_strategy: str | None = None
    confidence_threshold: float | None = None
    auto_merge: bool | None = None
    is_active: bool | None = None


class CheckBody(BaseModel):
    contact_data: dict


@router.post("", response_model=RuleOut, status_code=201)
async def create_rule(
    body: RuleCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.create_rule(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[RuleOut])
async def list_rules(
    is_active: bool | None = None, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_rules(db, actor["org_id"], is_active=is_active)


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
    rule_id: int, body: RuleUpdate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
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


@router.post("/check")
async def check_duplicates(
    body: CheckBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.check_duplicates(db, actor["org_id"], body.contact_data)
