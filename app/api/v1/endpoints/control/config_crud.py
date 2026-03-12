"""CRUD for control config: contact policies, money matrix, recruitment routing rules."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.contact_send_policy import ContactSendPolicy
from app.models.money_approval_matrix import MoneyApprovalMatrix
from app.models.recruitment_routing_rule import RecruitmentRoutingRule

router = APIRouter(prefix="/config", tags=["Control Config"])


def _org(actor: dict) -> int:
    return int(actor["org_id"])


# ── Contact send policies ────────────────────────────────────────────────────


class ContactSendPolicyCreate(BaseModel):
    channel: str = Field(..., max_length=50)
    max_per_contact_per_day: int = Field(..., ge=1, le=100)


class ContactSendPolicyUpdate(BaseModel):
    max_per_contact_per_day: int | None = Field(None, ge=1, le=100)


class ContactSendPolicyRead(BaseModel):
    id: int
    organization_id: int
    channel: str
    max_per_contact_per_day: int
    created_at: str | None

    model_config = {"from_attributes": True}


@router.get("/contact-policies", response_model=list[ContactSendPolicyRead])
async def list_contact_policies(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list:
    result = await db.execute(
        select(ContactSendPolicy)
        .where(ContactSendPolicy.organization_id == _org(actor))
        .order_by(ContactSendPolicy.channel)
    )
    rows = result.scalars().all()
    return [
        ContactSendPolicyRead(
            id=r.id,
            organization_id=r.organization_id,
            channel=r.channel,
            max_per_contact_per_day=r.max_per_contact_per_day,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.post("/contact-policies", response_model=ContactSendPolicyRead, status_code=201)
async def create_contact_policy(
    data: ContactSendPolicyCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ContactSendPolicyRead:
    existing = await db.execute(
        select(ContactSendPolicy).where(
            ContactSendPolicy.organization_id == _org(actor),
            ContactSendPolicy.channel == data.channel,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"Policy for channel {data.channel!r} already exists")
    row = ContactSendPolicy(
        organization_id=_org(actor),
        channel=data.channel,
        max_per_contact_per_day=data.max_per_contact_per_day,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ContactSendPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        channel=row.channel,
        max_per_contact_per_day=row.max_per_contact_per_day,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.put("/contact-policies/{policy_id}", response_model=ContactSendPolicyRead)
async def update_contact_policy(
    policy_id: int,
    data: ContactSendPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ContactSendPolicyRead:
    result = await db.execute(
        select(ContactSendPolicy).where(
            ContactSendPolicy.id == policy_id,
            ContactSendPolicy.organization_id == _org(actor),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Policy not found")
    if data.max_per_contact_per_day is not None:
        row.max_per_contact_per_day = data.max_per_contact_per_day
    await db.commit()
    await db.refresh(row)
    return ContactSendPolicyRead(
        id=row.id,
        organization_id=row.organization_id,
        channel=row.channel,
        max_per_contact_per_day=row.max_per_contact_per_day,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.delete("/contact-policies/{policy_id}", status_code=204)
async def delete_contact_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    result = await db.execute(
        select(ContactSendPolicy).where(
            ContactSendPolicy.id == policy_id,
            ContactSendPolicy.organization_id == _org(actor),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Policy not found")
    await db.delete(row)
    await db.commit()


# ── Money approval matrix ────────────────────────────────────────────────────


class MoneyApprovalMatrixCreate(BaseModel):
    action_type: str = Field(..., max_length=50)
    amount_min: float = Field(..., ge=0)
    amount_max: float = Field(..., ge=0)
    allowed_roles: list[str] = Field(..., min_length=1)


class MoneyApprovalMatrixUpdate(BaseModel):
    amount_min: float | None = Field(None, ge=0)
    amount_max: float | None = Field(None, ge=0)
    allowed_roles: list[str] | None = None


class MoneyApprovalMatrixRead(BaseModel):
    id: int
    organization_id: int
    action_type: str
    amount_min: float
    amount_max: float
    allowed_roles: list
    created_at: str | None

    model_config = {"from_attributes": True}


@router.get("/money-matrices", response_model=list[MoneyApprovalMatrixRead])
async def list_money_matrices(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list:
    result = await db.execute(
        select(MoneyApprovalMatrix)
        .where(MoneyApprovalMatrix.organization_id == _org(actor))
        .order_by(MoneyApprovalMatrix.action_type, MoneyApprovalMatrix.amount_min)
    )
    rows = result.scalars().all()
    return [
        MoneyApprovalMatrixRead(
            id=r.id,
            organization_id=r.organization_id,
            action_type=r.action_type,
            amount_min=r.amount_min,
            amount_max=r.amount_max,
            allowed_roles=r.allowed_roles or [],
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.post("/money-matrices", response_model=MoneyApprovalMatrixRead, status_code=201)
async def create_money_matrix(
    data: MoneyApprovalMatrixCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> MoneyApprovalMatrixRead:
    if data.amount_max < data.amount_min:
        raise HTTPException(400, "amount_max must be >= amount_min")
    row = MoneyApprovalMatrix(
        organization_id=_org(actor),
        action_type=data.action_type,
        amount_min=data.amount_min,
        amount_max=data.amount_max,
        allowed_roles=[r.upper() for r in data.allowed_roles],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return MoneyApprovalMatrixRead(
        id=row.id,
        organization_id=row.organization_id,
        action_type=row.action_type,
        amount_min=row.amount_min,
        amount_max=row.amount_max,
        allowed_roles=row.allowed_roles or [],
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.put("/money-matrices/{matrix_id}", response_model=MoneyApprovalMatrixRead)
async def update_money_matrix(
    matrix_id: int,
    data: MoneyApprovalMatrixUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> MoneyApprovalMatrixRead:
    result = await db.execute(
        select(MoneyApprovalMatrix).where(
            MoneyApprovalMatrix.id == matrix_id,
            MoneyApprovalMatrix.organization_id == _org(actor),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Matrix row not found")
    if data.amount_min is not None:
        row.amount_min = data.amount_min
    if data.amount_max is not None:
        row.amount_max = data.amount_max
    if data.allowed_roles is not None:
        row.allowed_roles = [r.upper() for r in data.allowed_roles]
    if row.amount_max < row.amount_min:
        raise HTTPException(400, "amount_max must be >= amount_min")
    await db.commit()
    await db.refresh(row)
    return MoneyApprovalMatrixRead(
        id=row.id,
        organization_id=row.organization_id,
        action_type=row.action_type,
        amount_min=row.amount_min,
        amount_max=row.amount_max,
        allowed_roles=row.allowed_roles or [],
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.delete("/money-matrices/{matrix_id}", status_code=204)
async def delete_money_matrix(
    matrix_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    result = await db.execute(
        select(MoneyApprovalMatrix).where(
            MoneyApprovalMatrix.id == matrix_id,
            MoneyApprovalMatrix.organization_id == _org(actor),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Matrix row not found")
    await db.delete(row)
    await db.commit()


# ── Recruitment routing rules ─────────────────────────────────────────────────


class RecruitmentRoutingRuleCreate(BaseModel):
    region: str | None = Field(None, max_length=100)
    product_line: str | None = Field(None, max_length=100)
    priority: int = Field(0, ge=0)
    assign_to_user_id: int | None = Field(None, ge=1)


class RecruitmentRoutingRuleUpdate(BaseModel):
    region: str | None = Field(None, max_length=100)
    product_line: str | None = Field(None, max_length=100)
    priority: int | None = Field(None, ge=0)
    assign_to_user_id: int | None = Field(None, ge=1)


class RecruitmentRoutingRuleRead(BaseModel):
    id: int
    organization_id: int
    region: str | None
    product_line: str | None
    priority: int
    assign_to_user_id: int | None
    created_at: str | None

    model_config = {"from_attributes": True}


@router.get("/recruitment-routing-rules", response_model=list[RecruitmentRoutingRuleRead])
async def list_recruitment_routing_rules(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list:
    result = await db.execute(
        select(RecruitmentRoutingRule)
        .where(RecruitmentRoutingRule.organization_id == _org(actor))
        .order_by(RecruitmentRoutingRule.priority.desc(), RecruitmentRoutingRule.id)
    )
    rows = result.scalars().all()
    return [
        RecruitmentRoutingRuleRead(
            id=r.id,
            organization_id=r.organization_id,
            region=r.region,
            product_line=r.product_line,
            priority=r.priority,
            assign_to_user_id=r.assign_to_user_id,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


@router.post("/recruitment-routing-rules", response_model=RecruitmentRoutingRuleRead, status_code=201)
async def create_recruitment_routing_rule(
    data: RecruitmentRoutingRuleCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RecruitmentRoutingRuleRead:
    row = RecruitmentRoutingRule(
        organization_id=_org(actor),
        region=data.region or None,
        product_line=data.product_line or None,
        priority=data.priority,
        assign_to_user_id=data.assign_to_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return RecruitmentRoutingRuleRead(
        id=row.id,
        organization_id=row.organization_id,
        region=row.region,
        product_line=row.product_line,
        priority=row.priority,
        assign_to_user_id=row.assign_to_user_id,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.put("/recruitment-routing-rules/{rule_id}", response_model=RecruitmentRoutingRuleRead)
async def update_recruitment_routing_rule(
    rule_id: int,
    data: RecruitmentRoutingRuleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> RecruitmentRoutingRuleRead:
    result = await db.execute(
        select(RecruitmentRoutingRule).where(
            RecruitmentRoutingRule.id == rule_id,
            RecruitmentRoutingRule.organization_id == _org(actor),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Rule not found")
    if data.region is not None:
        row.region = data.region or None
    if data.product_line is not None:
        row.product_line = data.product_line or None
    if data.priority is not None:
        row.priority = data.priority
    if data.assign_to_user_id is not None:
        row.assign_to_user_id = data.assign_to_user_id
    await db.commit()
    await db.refresh(row)
    return RecruitmentRoutingRuleRead(
        id=row.id,
        organization_id=row.organization_id,
        region=row.region,
        product_line=row.product_line,
        priority=row.priority,
        assign_to_user_id=row.assign_to_user_id,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.delete("/recruitment-routing-rules/{rule_id}", status_code=204)
async def delete_recruitment_routing_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    result = await db.execute(
        select(RecruitmentRoutingRule).where(
            RecruitmentRoutingRule.id == rule_id,
            RecruitmentRoutingRule.organization_id == _org(actor),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Rule not found")
    await db.delete(row)
    await db.commit()
