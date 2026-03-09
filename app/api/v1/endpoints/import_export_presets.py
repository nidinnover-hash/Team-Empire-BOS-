"""Import/export presets — saved column mappings and configurations."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import import_export_preset as preset_service

router = APIRouter(prefix="/import-export-presets", tags=["Import/Export Presets"])


class PresetCreate(BaseModel):
    name: str = Field(..., max_length=200)
    direction: str = Field(..., pattern=r"^(import|export)$")
    entity_type: str = Field(..., pattern=r"^(contact|deal|task)$")
    column_mapping: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


class PresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    direction: str
    entity_type: str
    column_mapping_json: str
    config_json: str
    is_active: bool
    created_at: datetime | None = None


@router.get("", response_model=list[PresetRead])
async def list_presets(
    direction: str | None = Query(None),
    entity_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[PresetRead]:
    items = await preset_service.list_presets(
        db, organization_id=actor["org_id"], direction=direction, entity_type=entity_type,
    )
    return [PresetRead.model_validate(p, from_attributes=True) for p in items]


@router.post("", response_model=PresetRead, status_code=201)
async def create_preset(
    data: PresetCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> PresetRead:
    preset = await preset_service.create_preset(
        db, organization_id=actor["org_id"], created_by=int(actor["id"]),
        name=data.name, direction=data.direction, entity_type=data.entity_type,
        column_mapping=data.column_mapping, config=data.config,
    )
    return PresetRead.model_validate(preset, from_attributes=True)


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await preset_service.delete_preset(db, preset_id=preset_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Preset not found")
