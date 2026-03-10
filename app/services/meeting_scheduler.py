"""Meeting scheduler service."""
from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting_scheduler import AvailabilitySlot, MeetingBooking


async def set_availability(
    db: AsyncSession, *, organization_id: int, user_id: int,
    day_of_week: int, start_time: str, end_time: str,
    is_active: bool = True,
) -> AvailabilitySlot:
    row = AvailabilitySlot(
        organization_id=organization_id, user_id=user_id,
        day_of_week=day_of_week, start_time=start_time,
        end_time=end_time, is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_availability(
    db: AsyncSession, organization_id: int, user_id: int,
) -> list[AvailabilitySlot]:
    q = (
        select(AvailabilitySlot)
        .where(AvailabilitySlot.organization_id == organization_id, AvailabilitySlot.user_id == user_id, AvailabilitySlot.is_active == True)  # noqa: E712
        .order_by(AvailabilitySlot.day_of_week, AvailabilitySlot.start_time)
    )
    return list((await db.execute(q)).scalars().all())


async def delete_slot(db: AsyncSession, slot_id: int, organization_id: int) -> bool:
    q = select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id, AvailabilitySlot.organization_id == organization_id)
    row = (await db.execute(q)).scalar_one_or_none()
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def create_booking(
    db: AsyncSession, *, organization_id: int, host_user_id: int,
    title: str, start_at, end_at, contact_id: int | None = None,
    location: str | None = None, notes: str | None = None,
    status: str = "confirmed",
) -> MeetingBooking:
    row = MeetingBooking(
        organization_id=organization_id, host_user_id=host_user_id,
        title=title, start_at=start_at, end_at=end_at,
        contact_id=contact_id, location=location, notes=notes,
        status=status,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_bookings(
    db: AsyncSession, organization_id: int, *,
    host_user_id: int | None = None, status: str | None = None,
    limit: int = 50,
) -> list[MeetingBooking]:
    q = select(MeetingBooking).where(MeetingBooking.organization_id == organization_id)
    if host_user_id is not None:
        q = q.where(MeetingBooking.host_user_id == host_user_id)
    if status:
        q = q.where(MeetingBooking.status == status)
    q = q.order_by(MeetingBooking.start_at.desc()).limit(limit)
    return list((await db.execute(q)).scalars().all())


async def get_booking(db: AsyncSession, booking_id: int, organization_id: int) -> MeetingBooking | None:
    q = select(MeetingBooking).where(MeetingBooking.id == booking_id, MeetingBooking.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def cancel_booking(db: AsyncSession, booking_id: int, organization_id: int) -> MeetingBooking | None:
    row = await get_booking(db, booking_id, organization_id)
    if not row:
        return None
    row.status = "cancelled"
    await db.commit()
    await db.refresh(row)
    return row
