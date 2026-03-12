"""Deal collaboration endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import deal_collaborator as svc

router = APIRouter(prefix="/deal-collaborators", tags=["deal-collaborators"])


class CollabOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    deal_id: int
    user_id: int
    role: str
    notes: str | None = None
    added_by_user_id: int | None = None
    created_at: datetime


class CollabCreate(BaseModel):
    deal_id: int
    user_id: int
    role: str = "support"
    notes: str | None = None


class CollabUpdate(BaseModel):
    role: str | None = None
    notes: str | None = None


@router.post("", response_model=CollabOut, status_code=201)
async def add_collaborator(
    data: CollabCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.add_collaborator(
        db, organization_id=actor["org_id"],
        added_by_user_id=actor["id"], **data.model_dump(),
    )


@router.get("/{deal_id}", response_model=list[CollabOut])
async def list_collaborators(
    deal_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_collaborators(db, actor["org_id"], deal_id)


@router.patch("/{collab_id}", response_model=CollabOut)
async def update_collaborator(
    collab_id: int, data: CollabUpdate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_collaborator(db, collab_id, actor["org_id"], **data.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Collaborator not found")
    return row


@router.delete("/{collab_id}", status_code=204)
async def remove_collaborator(
    collab_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.remove_collaborator(db, collab_id, actor["org_id"]):
        raise HTTPException(404, "Collaborator not found")


@router.get("/user/{user_id}", response_model=list[CollabOut])
async def get_user_deals(
    user_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_user_deals(db, actor["org_id"], user_id)
