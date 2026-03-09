"""Email suppression endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_roles
from app.core.deps import get_db
from app.services import email_suppression as svc

router = APIRouter(prefix="/email-suppressions", tags=["email-suppressions"])


class SuppressionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; organization_id: int; email_or_domain: str
    suppression_type: str; reason: str | None = None
    source: str; bounce_count: int
    details_json: str | None = None; created_at: datetime


class SuppressionCreate(BaseModel):
    email_or_domain: str; suppression_type: str
    reason: str | None = None; source: str = "manual"


@router.post("", response_model=SuppressionOut, status_code=201)
async def add_suppression(
    data: SuppressionCreate,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.add_suppression(db, organization_id=actor["org_id"], **data.model_dump())


@router.get("", response_model=list[SuppressionOut])
async def list_suppressions(
    suppression_type: str | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_suppressions(db, actor["org_id"], suppression_type=suppression_type)


@router.get("/check")
async def check_suppressed(
    email: str,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    suppressed = await svc.check_suppressed(db, actor["org_id"], email)
    return {"email": email, "suppressed": suppressed}


@router.get("/stats")
async def get_stats(
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_stats(db, actor["org_id"])


@router.delete("/{suppression_id}", status_code=204)
async def remove_suppression(
    suppression_id: int,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    if not await svc.remove_suppression(db, suppression_id, actor["org_id"]):
        raise HTTPException(404, "Suppression not found")
