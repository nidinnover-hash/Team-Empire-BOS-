"""Field-level audit log — track individual field changes on entities."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import field_audit as fa_service

router = APIRouter(prefix="/field-audit", tags=["Field Audit"])


class FieldChangeCreate(BaseModel):
    entity_type: str = Field(..., max_length=30)
    entity_id: int
    field_name: str = Field(..., max_length=100)
    old_value: str | None = None
    new_value: str | None = None
    change_source: str = Field("api", pattern=r"^(api|import|automation|merge)$")


class FieldChangeBatch(BaseModel):
    entity_type: str = Field(..., max_length=30)
    entity_id: int
    changes: list[dict]
    change_source: str = Field("api", pattern=r"^(api|import|automation|merge)$")


class FieldAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    field_name: str
    old_value: str | None = None
    new_value: str | None = None
    changed_by_user_id: int | None = None
    change_source: str
    created_at: datetime | None = None


@router.get("/entity/{entity_type}/{entity_id}", response_model=list[FieldAuditRead])
async def get_entity_history(
    entity_type: str,
    entity_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[FieldAuditRead]:
    items = await fa_service.get_entity_history(
        db, organization_id=actor["org_id"], entity_type=entity_type,
        entity_id=entity_id, limit=limit,
    )
    return [FieldAuditRead.model_validate(e, from_attributes=True) for e in items]


@router.get("/field/{entity_type}/{entity_id}/{field_name}", response_model=list[FieldAuditRead])
async def get_field_history(
    entity_type: str,
    entity_id: int,
    field_name: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[FieldAuditRead]:
    items = await fa_service.get_field_history(
        db, organization_id=actor["org_id"], entity_type=entity_type,
        entity_id=entity_id, field_name=field_name, limit=limit,
    )
    return [FieldAuditRead.model_validate(e, from_attributes=True) for e in items]


@router.post("", response_model=FieldAuditRead, status_code=201)
async def record_field_change(
    data: FieldChangeCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> FieldAuditRead:
    entry = await fa_service.record_change(
        db, organization_id=actor["org_id"],
        entity_type=data.entity_type, entity_id=data.entity_id,
        field_name=data.field_name, old_value=data.old_value,
        new_value=data.new_value, changed_by=int(actor["id"]),
        change_source=data.change_source,
    )
    return FieldAuditRead.model_validate(entry, from_attributes=True)


@router.post("/batch", response_model=list[FieldAuditRead], status_code=201)
async def record_field_changes_batch(
    data: FieldChangeBatch,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[FieldAuditRead]:
    entries = await fa_service.record_changes_batch(
        db, organization_id=actor["org_id"],
        entity_type=data.entity_type, entity_id=data.entity_id,
        changes=data.changes, changed_by=int(actor["id"]),
        change_source=data.change_source,
    )
    return [FieldAuditRead.model_validate(e, from_attributes=True) for e in entries]


@router.get("/recent", response_model=list[FieldAuditRead])
async def get_recent_changes(
    entity_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[FieldAuditRead]:
    items = await fa_service.get_recent_changes(
        db, organization_id=actor["org_id"], entity_type=entity_type, limit=limit,
    )
    return [FieldAuditRead.model_validate(e, from_attributes=True) for e in items]
