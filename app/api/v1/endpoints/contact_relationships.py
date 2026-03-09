"""Contact relationship mapping endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import contact_relationship as svc

router = APIRouter(prefix="/contact-relationships", tags=["contact-relationships"])


class RelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    contact_a_id: int
    contact_b_id: int
    relationship_type: str
    strength: int
    notes: str | None = None
    created_at: datetime


class RelCreate(BaseModel):
    contact_a_id: int
    contact_b_id: int
    relationship_type: str
    strength: int = 50
    notes: str | None = None


class RelUpdate(BaseModel):
    relationship_type: str | None = None
    strength: int | None = None
    notes: str | None = None


@router.post("", response_model=RelOut, status_code=201)
async def create_relationship(
    data: RelCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_relationship(
        db, organization_id=actor["org_id"], **data.model_dump(),
    )


@router.get("", response_model=list[RelOut])
async def list_relationships(
    contact_id: int | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_relationships(db, actor["org_id"], contact_id=contact_id)


@router.patch("/{rel_id}", response_model=RelOut)
async def update_relationship(
    rel_id: int,
    data: RelUpdate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_relationship(
        db, rel_id, actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if not row:
        raise HTTPException(404, "Relationship not found")
    return row


@router.delete("/{rel_id}", status_code=204)
async def delete_relationship(
    rel_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.delete_relationship(db, rel_id, actor["org_id"]):
        raise HTTPException(404, "Relationship not found")
