"""Custom fields — user-defined metadata on entities."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import custom_field as cf_service

router = APIRouter(prefix="/custom-fields", tags=["Custom Fields"])


class FieldDefinitionCreate(BaseModel):
    entity_type: str = Field(..., pattern=r"^(contact|deal|task|project)$")
    field_key: str = Field(..., max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    field_label: str = Field(..., max_length=200)
    field_type: str = Field("text", pattern=r"^(text|number|date|boolean|select)$")
    options: list[str] | None = None
    is_required: bool = False
    sort_order: int = 0


class FieldDefinitionUpdate(BaseModel):
    field_label: str | None = Field(None, max_length=200)
    options: list[str] | None = None
    is_required: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class FieldDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    field_key: str
    field_label: str
    field_type: str
    options_json: str | None = None
    is_required: bool
    is_active: bool
    sort_order: int
    created_at: datetime | None = None


class SetValueRequest(BaseModel):
    field_definition_id: int
    entity_id: int
    value: str


@router.get("/definitions", response_model=list[FieldDefinitionRead])
async def list_field_definitions(
    entity_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[FieldDefinitionRead]:
    items = await cf_service.list_definitions(db, organization_id=actor["org_id"], entity_type=entity_type)
    return [FieldDefinitionRead.model_validate(d, from_attributes=True) for d in items]


@router.post("/definitions", response_model=FieldDefinitionRead, status_code=201)
async def create_field_definition(
    data: FieldDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> FieldDefinitionRead:
    defn = await cf_service.create_definition(
        db, organization_id=actor["org_id"],
        entity_type=data.entity_type, field_key=data.field_key,
        field_label=data.field_label, field_type=data.field_type,
        options=data.options, is_required=data.is_required,
        sort_order=data.sort_order,
    )
    return FieldDefinitionRead.model_validate(defn, from_attributes=True)


@router.patch("/definitions/{defn_id}", response_model=FieldDefinitionRead)
async def update_field_definition(
    defn_id: int,
    data: FieldDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> FieldDefinitionRead:
    defn = await cf_service.update_definition(
        db, defn_id=defn_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if defn is None:
        raise HTTPException(status_code=404, detail="Field definition not found")
    return FieldDefinitionRead.model_validate(defn, from_attributes=True)


@router.delete("/definitions/{defn_id}", status_code=204)
async def delete_field_definition(
    defn_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await cf_service.delete_definition(db, defn_id=defn_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Field definition not found")


@router.post("/values")
async def set_field_value(
    data: SetValueRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    val = await cf_service.set_value(
        db, field_definition_id=data.field_definition_id,
        entity_id=data.entity_id, value=data.value,
    )
    return {"id": val.id, "field_definition_id": val.field_definition_id, "entity_id": val.entity_id, "value": val.value_text}


@router.get("/values/{entity_type}/{entity_id}")
async def get_field_values(
    entity_type: str,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    return await cf_service.get_values(db, entity_type=entity_type, entity_id=entity_id, organization_id=actor["org_id"])
