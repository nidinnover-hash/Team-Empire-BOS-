"""Revenue recognition endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import revenue_recognition as svc

router = APIRouter(prefix="/revenue", tags=["revenue"])


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    deal_id: int | None = None
    period: str
    total_amount: float
    recognized_amount: float
    deferred_amount: float
    recognition_stage: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class EntryCreate(BaseModel):
    period: str
    total_amount: float
    recognized_amount: float = 0.0
    deferred_amount: float = 0.0
    recognition_stage: str = "contract"
    deal_id: int | None = None
    notes: str | None = None


class EntryUpdate(BaseModel):
    recognized_amount: float | None = None
    deferred_amount: float | None = None
    recognition_stage: str | None = None
    notes: str | None = None


@router.post("", response_model=EntryOut, status_code=201)
async def create_entry(
    data: EntryCreate,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.create_entry(db, organization_id=actor["org_id"], **data.model_dump())


@router.get("", response_model=list[EntryOut])
async def list_entries(
    period: str | None = None, deal_id: int | None = None,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.list_entries(db, actor["org_id"], period=period, deal_id=deal_id)


@router.get("/summary/{period}")
async def get_period_summary(
    period: str,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    return await svc.get_period_summary(db, actor["org_id"], period)


@router.get("/{entry_id}", response_model=EntryOut)
async def get_entry(
    entry_id: int,
    actor=Depends(require_roles("CEO", "ADMIN", "MANAGER")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.get_entry(db, entry_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Revenue entry not found")
    return row


@router.patch("/{entry_id}", response_model=EntryOut)
async def update_entry(
    entry_id: int, data: EntryUpdate,
    actor=Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    row = await svc.update_entry(db, entry_id, actor["org_id"], **data.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Revenue entry not found")
    return row
