"""Document signing endpoints."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import document_signing as svc

router = APIRouter(prefix="/document-signing", tags=["document-signing"])


class SignatureRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    title: str
    document_url: str | None = None
    deal_id: int | None = None
    contact_id: int | None = None
    status: str
    signing_order: int
    expires_at: date | None = None
    signed_at: datetime | None = None
    sent_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class RequestCreate(BaseModel):
    title: str
    document_url: str | None = None
    deal_id: int | None = None
    contact_id: int | None = None
    signing_order: int = 1
    signers: list[dict] | None = None
    expires_at: date | None = None


@router.post("", response_model=SignatureRequestOut, status_code=201)
async def create_request(
    body: RequestCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_request(db, organization_id=actor["org_id"], sent_by_user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[SignatureRequestOut])
async def list_requests(
    status: str | None = None, deal_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_requests(db, actor["org_id"], status=status, deal_id=deal_id)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_stats(db, actor["org_id"])


@router.get("/{request_id}", response_model=SignatureRequestOut)
async def get_request(
    request_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_request(db, request_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Signature request not found")
    return row


@router.post("/{request_id}/sign", response_model=SignatureRequestOut)
async def mark_signed(
    request_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.mark_signed(db, request_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Signature request not found")
    return row


@router.post("/{request_id}/decline", response_model=SignatureRequestOut)
async def mark_declined(
    request_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.mark_declined(db, request_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Signature request not found")
    return row
