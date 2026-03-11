"""Subscription management endpoints."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import subscription as svc

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    billing_cycle: str
    price: float
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PlanCreate(BaseModel):
    name: str
    billing_cycle: str = "monthly"
    price: float = 0
    currency: str = "USD"
    features: list[str] | None = None
    is_active: bool = True


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    plan_id: int
    contact_id: int | None = None
    status: str
    start_date: date
    end_date: date | None = None
    next_billing_date: date | None = None
    mrr: float
    created_at: datetime
    updated_at: datetime


class SubscriptionCreate(BaseModel):
    plan_id: int
    contact_id: int | None = None
    start_date: date
    end_date: date | None = None
    next_billing_date: date | None = None
    mrr: float = 0
    status: str = "active"


class SubscriptionUpdate(BaseModel):
    status: str | None = None
    end_date: date | None = None
    next_billing_date: date | None = None
    mrr: float | None = None
    plan_id: int | None = None


@router.post("/plans", response_model=PlanOut, status_code=201)
async def create_plan(
    body: PlanCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.create_plan(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    is_active: bool | None = None, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_plans(db, actor["org_id"], is_active=is_active)


@router.post("", response_model=SubscriptionOut, status_code=201)
async def create_subscription(
    body: SubscriptionCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_subscription(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[SubscriptionOut])
async def list_subscriptions(
    status: str | None = None, plan_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_subscriptions(db, actor["org_id"], status=status, plan_id=plan_id)


@router.get("/mrr-summary")
async def get_mrr_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_mrr_summary(db, actor["org_id"])


@router.get("/{sub_id}", response_model=SubscriptionOut)
async def get_subscription(
    sub_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_subscription(db, sub_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Subscription not found")
    return row


@router.put("/{sub_id}", response_model=SubscriptionOut)
async def update_subscription(
    sub_id: int, body: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_subscription(db, sub_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Subscription not found")
    return row


@router.post("/{sub_id}/cancel", response_model=SubscriptionOut)
async def cancel_subscription(
    sub_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    row = await svc.cancel_subscription(db, sub_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Subscription not found")
    return row
