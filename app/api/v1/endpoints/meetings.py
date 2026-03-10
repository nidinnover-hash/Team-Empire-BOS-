"""Meeting scheduler endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import meeting_scheduler as svc

router = APIRouter(prefix="/meetings", tags=["meetings"])


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    user_id: int
    day_of_week: int
    start_time: str
    end_time: str
    is_active: bool
    created_at: datetime


class SlotCreate(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    host_user_id: int
    contact_id: int | None = None
    title: str
    start_at: datetime
    end_at: datetime
    status: str
    location: str | None = None
    notes: str | None = None
    reminder_sent: bool
    created_at: datetime


class BookingCreate(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime
    contact_id: int | None = None
    location: str | None = None
    notes: str | None = None


@router.post("/availability", response_model=SlotOut, status_code=201)
async def set_availability(
    body: SlotCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.set_availability(db, organization_id=actor["org_id"], user_id=actor["id"], **body.model_dump())


@router.get("/availability/{user_id}", response_model=list[SlotOut])
async def list_availability(
    user_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_availability(db, actor["org_id"], user_id)


@router.delete("/availability/{slot_id}", status_code=204)
async def delete_slot(
    slot_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    ok = await svc.delete_slot(db, slot_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Slot not found")


@router.post("/bookings", response_model=BookingOut, status_code=201)
async def create_booking(
    body: BookingCreate, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_booking(db, organization_id=actor["org_id"], host_user_id=actor["id"], **body.model_dump())


@router.get("/bookings", response_model=list[BookingOut])
async def list_bookings(
    host_user_id: int | None = None, status: str | None = None,
    limit: int = 50, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_bookings(db, actor["org_id"], host_user_id=host_user_id, status=status, limit=limit)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
async def cancel_booking(
    booking_id: int, db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.cancel_booking(db, booking_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Booking not found")
    return row
