"""Commission calculator endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import commission as svc

router = APIRouter(prefix="/commissions", tags=["commissions"])


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    deal_type: str | None = None
    stage: str | None = None
    rate_percent: float
    min_deal_value: int
    max_deal_value: int | None = None
    is_active: bool
    created_at: datetime


class RuleCreate(BaseModel):
    name: str
    rate_percent: float = 10.0
    deal_type: str | None = None
    stage: str | None = None
    min_deal_value: int = 0
    max_deal_value: int | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    rate_percent: float | None = None
    deal_type: str | None = None
    stage: str | None = None
    is_active: bool | None = None


class PayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    rule_id: int
    deal_id: int
    user_id: int
    deal_value: int
    commission_amount: float
    split_percent: float
    status: str
    notes: str | None = None
    created_at: datetime


class PayoutCreate(BaseModel):
    rule_id: int
    deal_id: int
    user_id: int
    deal_value: int
    split_percent: float = 100.0
    notes: str | None = None


class PayoutStatusUpdate(BaseModel):
    status: str


@router.post("/rules", response_model=RuleOut, status_code=201)
async def create_rule(
    data: RuleCreate,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_rule(db, organization_id=actor["org_id"], **data.model_dump())


@router.get("/rules", response_model=list[RuleOut])
async def list_rules(
    is_active: bool | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_rules(db, actor["org_id"], is_active=is_active)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: int, data: RuleUpdate,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_rule(db, rule_id, actor["org_id"], **data.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Rule not found")
    return row


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_rule(db, rule_id, actor["org_id"]):
        raise HTTPException(404, "Rule not found")


@router.post("/payouts", response_model=PayoutOut, status_code=201)
async def calculate_payout(
    data: PayoutCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.calculate_payout(db, organization_id=actor["org_id"], **data.model_dump())


@router.get("/payouts", response_model=list[PayoutOut])
async def list_payouts(
    user_id: int | None = None, status: str | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_payouts(db, actor["org_id"], user_id=user_id, status=status)


@router.patch("/payouts/{payout_id}", response_model=PayoutOut)
async def update_payout_status(
    payout_id: int, data: PayoutStatusUpdate,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_payout_status(db, payout_id, actor["org_id"], data.status)
    if not row:
        raise HTTPException(404, "Payout not found")
    return row


@router.get("/summary")
async def get_summary(
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_summary(db, actor["org_id"])
