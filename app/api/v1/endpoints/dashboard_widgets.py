"""Dashboard widget library — reusable widget definitions."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import dashboard_widget as widget_service

router = APIRouter(prefix="/dashboard-widgets", tags=["Dashboard Widgets"])


class WidgetCreate(BaseModel):
    name: str = Field(..., max_length=200)
    widget_type: str = Field(..., pattern=r"^(chart|metric|table|list)$")
    data_source: str = Field(..., max_length=100)
    config: dict = Field(default_factory=dict)
    default_width: int = Field(4, ge=1, le=12)
    default_height: int = Field(3, ge=1, le=12)


class WidgetUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    config: dict | None = None
    default_width: int | None = Field(None, ge=1, le=12)
    default_height: int | None = Field(None, ge=1, le=12)


class WidgetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    widget_type: str
    data_source: str
    config_json: str
    default_width: int
    default_height: int
    is_system: bool
    is_active: bool
    created_at: datetime | None = None


@router.get("", response_model=list[WidgetRead])
async def list_widgets(
    widget_type: str | None = Query(None),
    data_source: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[WidgetRead]:
    items = await widget_service.list_widgets(
        db, organization_id=actor["org_id"], widget_type=widget_type, data_source=data_source,
    )
    return [WidgetRead.model_validate(w, from_attributes=True) for w in items]


@router.post("", response_model=WidgetRead, status_code=201)
async def create_widget(
    data: WidgetCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WidgetRead:
    widget = await widget_service.create_widget(
        db, organization_id=actor["org_id"], created_by=int(actor["id"]),
        name=data.name, widget_type=data.widget_type, data_source=data.data_source,
        config=data.config, default_width=data.default_width, default_height=data.default_height,
    )
    return WidgetRead.model_validate(widget, from_attributes=True)


@router.patch("/{widget_id}", response_model=WidgetRead)
async def update_widget(
    widget_id: int,
    data: WidgetUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WidgetRead:
    widget = await widget_service.update_widget(
        db, widget_id=widget_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    return WidgetRead.model_validate(widget, from_attributes=True)


@router.delete("/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await widget_service.delete_widget(db, widget_id=widget_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Widget not found")


@router.get("/catalog")
async def get_system_catalog(
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    """Return the built-in system widget catalog."""
    return await widget_service.get_system_widget_catalog()
