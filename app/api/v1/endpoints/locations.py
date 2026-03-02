from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.location import (
    EmployeeLocationRead,
    LocationCheckinCreate,
    LocationCheckinRead,
    LocationConsentUpdate,
    LocationTrackingCreate,
    LocationTrackingRead,
)
from app.services import location_service

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.post("/track", response_model=LocationTrackingRead, status_code=201)
async def track_location(
    data: LocationTrackingCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF", "EMPLOYEE")),
) -> LocationTrackingRead:
    """Record a GPS/IP/manual location data point."""
    point = await location_service.record_location(db, data, organization_id=actor["org_id"])
    await record_action(
        db,
        event_type="location_tracked",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="location_tracking",
        entity_id=point.id,
        payload_json={"employee_id": data.employee_id, "source": data.source},
    )
    return point


@router.get("/active", response_model=list[EmployeeLocationRead])
async def get_active_locations(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[EmployeeLocationRead]:
    """Get latest locations for all consented employees."""
    rows = await location_service.get_active_locations(db, organization_id=actor["org_id"])
    return [EmployeeLocationRead(**row) for row in rows]


@router.get("/history", response_model=list[LocationTrackingRead])
async def get_location_history(
    employee_id: int | None = Query(None),
    source: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[LocationTrackingRead]:
    """Get paginated location history with optional filters."""
    return await location_service.get_location_history(
        db,
        organization_id=actor["org_id"],
        employee_id=employee_id,
        source=source,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.post("/checkin", response_model=LocationCheckinRead, status_code=201)
async def create_checkin(
    data: LocationCheckinCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF", "EMPLOYEE")),
) -> LocationCheckinRead:
    """Create a manual check-in."""
    checkin = await location_service.create_checkin(db, data, organization_id=actor["org_id"])
    await record_action(
        db,
        event_type="location_checkin_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="location_checkin",
        entity_id=checkin.id,
        payload_json={"employee_id": data.employee_id, "type": data.checkin_type},
    )
    return checkin


@router.post("/checkin/{checkin_id}/checkout", response_model=LocationCheckinRead)
async def checkout(
    checkin_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF", "EMPLOYEE")),
) -> LocationCheckinRead:
    """Check out from a previous check-in."""
    checkin = await location_service.checkout(db, checkin_id, organization_id=actor["org_id"])
    if checkin is None:
        raise HTTPException(status_code=404, detail="Check-in not found")
    await record_action(
        db,
        event_type="location_checkout",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="location_checkin",
        entity_id=checkin_id,
    )
    return checkin


@router.get("/checkins", response_model=list[LocationCheckinRead])
async def list_checkins(
    employee_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[LocationCheckinRead]:
    """List check-ins with optional employee filter."""
    return await location_service.list_checkins(
        db, organization_id=actor["org_id"],
        employee_id=employee_id, limit=limit, offset=offset,
    )


@router.patch("/consent", status_code=200)
async def update_consent(
    data: LocationConsentUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF", "EMPLOYEE")),
) -> dict:
    """Toggle location tracking consent for an employee."""
    ok = await location_service.update_consent(db, data, organization_id=actor["org_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Employee not found")
    await record_action(
        db,
        event_type="location_consent_updated",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="employee",
        entity_id=data.employee_id,
        payload_json={"consent": data.consent},
    )
    return {"employee_id": data.employee_id, "consent": data.consent}


@router.get("/consent")
async def get_consent(
    employee_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF", "EMPLOYEE")),
) -> dict:
    """Get consent status for an employee."""
    status = await location_service.get_consent_status(
        db, employee_id, organization_id=actor["org_id"],
    )
    if status is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return status


@router.get("/consent/all")
async def get_all_consent(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[dict]:
    """Get consent status for all employees."""
    return await location_service.get_all_consent_status(db, organization_id=actor["org_id"])
