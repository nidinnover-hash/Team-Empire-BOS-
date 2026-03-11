"""Goal cascade tracking endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import goal_cascade as svc

router = APIRouter(prefix="/goal-cascades", tags=["goal-cascades"])


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    parent_type: str
    parent_id: int
    child_type: str
    child_id: int
    weight: float
    notes: str | None = None
    created_at: datetime


class LinkCreate(BaseModel):
    parent_type: str
    parent_id: int
    child_type: str
    child_id: int
    weight: float = 1.0
    notes: str | None = None


@router.post("", response_model=LinkOut, status_code=201)
async def create_link(
    data: LinkCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_link(
        db, organization_id=actor["org_id"], **data.model_dump(),
    )


@router.get("", response_model=list[LinkOut])
async def list_links(
    parent_type: str | None = None,
    parent_id: int | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_links(
        db, actor["org_id"], parent_type=parent_type, parent_id=parent_id,
    )


@router.get("/tree")
async def get_tree(
    root_type: str,
    root_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_tree(db, actor["org_id"], root_type, root_id)


@router.get("/children", response_model=list[LinkOut])
async def get_children(
    parent_type: str,
    parent_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_children(db, actor["org_id"], parent_type, parent_id)


@router.get("/parents", response_model=list[LinkOut])
async def get_parents(
    child_type: str,
    child_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_parents(db, actor["org_id"], child_type, child_id)


@router.delete("/{link_id}", status_code=204)
async def delete_link(
    link_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_link(db, link_id, actor["org_id"]):
        raise HTTPException(404, "Link not found")
