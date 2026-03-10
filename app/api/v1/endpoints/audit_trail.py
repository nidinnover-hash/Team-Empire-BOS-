"""Audit trail viewer endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import audit_entry as svc

router = APIRouter(prefix="/audit-trail", tags=["audit-trail"])


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    entity_type: str
    entity_id: int
    action: str
    user_id: int | None = None
    ip_address: str | None = None
    created_at: datetime


class RecordBody(BaseModel):
    entity_type: str
    entity_id: int
    action: str
    changes: dict | None = None
    snapshot: dict | None = None
    ip_address: str | None = None


@router.post("", response_model=AuditEntryOut, status_code=201)
async def record_audit(
    body: RecordBody, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.record_audit(db, organization_id=actor["org_id"], user_id=actor["id"], **body.model_dump())


@router.get("", response_model=list[AuditEntryOut])
async def list_entries(
    entity_type: str | None = None, entity_id: int | None = None,
    action: str | None = None, user_id: int | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_entries(db, actor["org_id"], entity_type=entity_type, entity_id=entity_id, action=action, user_id=user_id, limit=limit)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    return await svc.get_stats(db, actor["org_id"])


@router.get("/history/{entity_type}/{entity_id}", response_model=list[AuditEntryOut])
async def get_entity_history(
    entity_type: str, entity_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_entity_history(db, actor["org_id"], entity_type, entity_id)
