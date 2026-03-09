"""Role-based dashboards — default layouts per role."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import role_dashboard as rd_service

router = APIRouter(prefix="/role-dashboards", tags=["Role Dashboards"])


class RoleLayoutSave(BaseModel):
    role: str = Field(..., pattern=r"^(CEO|ADMIN|MANAGER)$")
    layout: list[dict] = Field(default_factory=list)
    theme: str = Field("default", max_length=20)


@router.get("")
async def list_all_role_layouts(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    return await rd_service.list_all_role_layouts(db, organization_id=actor["org_id"])


@router.get("/{role}")
async def get_role_layout(
    role: str,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    return await rd_service.get_role_layout(db, organization_id=actor["org_id"], role=role)


@router.put("")
async def save_role_layout(
    data: RoleLayoutSave,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    rd = await rd_service.save_role_layout(
        db, organization_id=actor["org_id"], role=data.role,
        layout=data.layout, theme=data.theme,
    )
    return {"id": rd.id, "role": rd.role, "theme": rd.theme, "saved": True}
