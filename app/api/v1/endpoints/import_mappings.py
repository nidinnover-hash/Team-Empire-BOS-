"""Contact import mapping endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import import_mapping as svc

router = APIRouter(prefix="/import-mappings", tags=["import-mappings"])


class MappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    name: str
    entity_type: str
    created_at: datetime
    updated_at: datetime


class MappingCreate(BaseModel):
    name: str
    entity_type: str = "contact"
    column_map: dict | None = None
    transformers: list[dict] | None = None


class MappingUpdate(BaseModel):
    name: str | None = None
    entity_type: str | None = None
    column_map: dict | None = None
    transformers: list[dict] | None = None


class ImportHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    mapping_id: int | None = None
    file_name: str
    entity_type: str
    total_rows: int
    success_rows: int
    error_rows: int
    status: str
    started_by_user_id: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RecordImportBody(BaseModel):
    file_name: str
    entity_type: str = "contact"
    mapping_id: int | None = None
    total_rows: int = 0
    success_rows: int = 0
    error_rows: int = 0
    status: str = "completed"
    errors: list[dict] | None = None


@router.post("", response_model=MappingOut, status_code=201)
async def create_mapping(
    body: MappingCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_mapping(db, organization_id=actor["org_id"], **body.model_dump())


@router.get("", response_model=list[MappingOut])
async def list_mappings(
    entity_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_mappings(db, actor["org_id"], entity_type=entity_type)


@router.get("/{mapping_id}", response_model=MappingOut)
async def get_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_mapping(db, mapping_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Mapping not found")
    return row


@router.put("/{mapping_id}", response_model=MappingOut)
async def update_mapping(
    mapping_id: int,
    body: MappingUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_mapping(db, mapping_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Mapping not found")
    return row


@router.delete("/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_mapping(db, mapping_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Mapping not found")


@router.post("/imports", response_model=ImportHistoryOut, status_code=201)
async def record_import(
    body: RecordImportBody,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.record_import(db, organization_id=actor["org_id"], started_by_user_id=actor["id"], **body.model_dump())


@router.get("/imports/history", response_model=list[ImportHistoryOut])
async def list_imports(
    entity_type: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_imports(db, actor["org_id"], entity_type=entity_type, limit=limit)


@router.get("/imports/stats")
async def get_import_stats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.get_import_stats(db, actor["org_id"])
