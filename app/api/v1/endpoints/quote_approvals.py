"""Quote approval endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import quote_approval as svc

router = APIRouter(prefix="/quote-approvals", tags=["quote-approvals"])


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    quote_id: int
    level: int
    approver_user_id: int
    status: str
    reason: str | None = None
    requested_by_user_id: int
    requested_at: datetime
    decided_at: datetime | None = None
    created_at: datetime


class ApprovalRequest(BaseModel):
    quote_id: int
    level: int = 1
    approver_user_id: int


class DecisionBody(BaseModel):
    status: str  # approved, rejected
    reason: str | None = None


@router.post("", response_model=ApprovalOut, status_code=201)
async def request_approval(
    body: ApprovalRequest, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.request_approval(db, organization_id=actor["org_id"], requested_by_user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    quote_id: int | None = None, status: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_approvals(db, actor["org_id"], quote_id=quote_id, status=status)


@router.put("/{approval_id}/decide", response_model=ApprovalOut)
async def decide(
    approval_id: int, body: DecisionBody,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    row = await svc.decide(db, approval_id, actor["org_id"], body.status, body.reason)
    if not row:
        raise HTTPException(404, "Approval not found")
    return row


@router.get("/pending")
async def get_pending_count(
    approver_user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_pending_count(db, actor["org_id"], approver_user_id=approver_user_id)
