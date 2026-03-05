import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.location_tracking import LocationCheckin, LocationTracking
from app.schemas.location import (
    LocationCheckinCreate,
    LocationConsentUpdate,
    LocationTrackingCreate,
)

logger = logging.getLogger(__name__)


async def record_location(
    db: AsyncSession,
    data: LocationTrackingCreate,
    organization_id: int,
) -> LocationTracking:
    """Record a new location point and mark it as the active one."""
    # Unmark previous active point for this employee
    await db.execute(
        update(LocationTracking)
        .where(
            LocationTracking.organization_id == organization_id,
            LocationTracking.employee_id == data.employee_id,
            LocationTracking.is_active.is_(True),
        )
        .values(is_active=False)
    )
    point = LocationTracking(
        organization_id=organization_id,
        **data.model_dump(),
    )
    db.add(point)
    await db.commit()
    await db.refresh(point)
    logger.info(
        "Location recorded id=%d employee=%d org=%d source=%s",
        point.id, data.employee_id, organization_id, data.source,
    )
    return point


async def get_active_locations(
    db: AsyncSession,
    organization_id: int,
) -> list[dict]:
    """Get latest location for all consented employees."""
    result = await db.execute(
        select(
            LocationTracking.employee_id,
            Employee.name.label("employee_name"),
            Employee.job_title.label("role"),
            LocationTracking.latitude,
            LocationTracking.longitude,
            LocationTracking.accuracy_m,
            LocationTracking.source,
            LocationTracking.address,
            LocationTracking.created_at.label("last_seen"),
        )
        .join(Employee, Employee.id == LocationTracking.employee_id)
        .where(
            LocationTracking.organization_id == organization_id,
            LocationTracking.is_active.is_(True),
            Employee.location_tracking_consent.is_(True),
            Employee.is_active.is_(True),
        )
        .order_by(LocationTracking.created_at.desc())
        .limit(500)
    )
    return [row._asdict() for row in result.all()]


async def get_location_history(
    db: AsyncSession,
    organization_id: int,
    employee_id: int | None = None,
    source: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[LocationTracking]:
    """Get paginated location history with optional filters."""
    q = select(LocationTracking).where(
        LocationTracking.organization_id == organization_id,
    )
    if employee_id is not None:
        q = q.where(LocationTracking.employee_id == employee_id)
    if source is not None:
        q = q.where(LocationTracking.source == source)
    if date_from is not None:
        q = q.where(LocationTracking.created_at >= date_from)
    if date_to is not None:
        q = q.where(LocationTracking.created_at <= date_to)
    q = q.order_by(LocationTracking.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def create_checkin(
    db: AsyncSession,
    data: LocationCheckinCreate,
    organization_id: int,
) -> LocationCheckin:
    """Create a manual check-in record."""
    checkin = LocationCheckin(
        organization_id=organization_id,
        **data.model_dump(),
    )
    db.add(checkin)
    await db.commit()
    await db.refresh(checkin)
    logger.info(
        "Checkin created id=%d employee=%d org=%d type=%s",
        checkin.id, data.employee_id, organization_id, data.checkin_type,
    )
    return checkin


async def checkout(
    db: AsyncSession,
    checkin_id: int,
    organization_id: int,
) -> LocationCheckin | None:
    """Mark a check-in as checked out."""
    result = await db.execute(
        select(LocationCheckin).where(
            LocationCheckin.id == checkin_id,
            LocationCheckin.organization_id == organization_id,
        )
    )
    checkin = result.scalar_one_or_none()
    if checkin is None:
        return None
    from datetime import UTC

    checkin.checked_out_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(checkin)
    logger.info("Checkout id=%d org=%d", checkin_id, organization_id)
    return checkin


async def list_checkins(
    db: AsyncSession,
    organization_id: int,
    employee_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[LocationCheckin]:
    """List check-ins with optional employee filter."""
    q = select(LocationCheckin).where(
        LocationCheckin.organization_id == organization_id,
    )
    if employee_id is not None:
        q = q.where(LocationCheckin.employee_id == employee_id)
    q = q.order_by(LocationCheckin.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_consent(
    db: AsyncSession,
    data: LocationConsentUpdate,
    organization_id: int,
) -> bool:
    """Toggle location tracking consent for an employee."""
    result = await db.execute(
        select(Employee).where(
            Employee.id == data.employee_id,
            Employee.organization_id == organization_id,
        )
    )
    emp = result.scalar_one_or_none()
    if emp is None:
        return False
    emp.location_tracking_consent = data.consent
    await db.commit()
    logger.info(
        "Location consent updated employee=%d org=%d consent=%s",
        data.employee_id, organization_id, data.consent,
    )
    return True


async def get_consent_status(
    db: AsyncSession,
    employee_id: int,
    organization_id: int,
) -> dict | None:
    """Check location tracking consent for an employee."""
    result = await db.execute(
        select(Employee.id, Employee.name, Employee.location_tracking_consent).where(
            Employee.id == employee_id,
            Employee.organization_id == organization_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    return {
        "employee_id": row.id,
        "name": row.name,
        "consent": row.location_tracking_consent,
    }


async def get_all_consent_status(
    db: AsyncSession,
    organization_id: int,
) -> list[dict]:
    """Get consent status for all employees in org."""
    result = await db.execute(
        select(Employee.id, Employee.name, Employee.location_tracking_consent).where(
            Employee.organization_id == organization_id,
            Employee.is_active.is_(True),
        )
        .order_by(Employee.name)
        .limit(500)
    )
    return [
        {"employee_id": row.id, "name": row.name, "consent": row.location_tracking_consent}
        for row in result.all()
    ]
