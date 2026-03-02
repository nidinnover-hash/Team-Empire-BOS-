from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.department import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.services import department as department_service

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=list[DepartmentRead])
async def list_departments(
    active_only: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[DepartmentRead]:
    return await department_service.list_departments(
        db, org_id=int(user["org_id"]), active_only=active_only, skip=skip, limit=limit,
    )


@router.get("/{department_id}", response_model=DepartmentRead)
async def get_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DepartmentRead:
    dept = await department_service.get_department(
        db, org_id=int(user["org_id"]), department_id=department_id,
    )
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept


@router.post("", response_model=DepartmentRead, status_code=201)
async def create_department(
    data: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DepartmentRead:
    dept = await department_service.create_department(
        db, org_id=int(user["org_id"]), data=data,
    )
    await record_action(
        db,
        event_type="department_created",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="department",
        entity_id=dept.id,
        payload_json={"name": dept.name, "code": dept.code},
    )
    return dept


@router.patch("/{department_id}", response_model=DepartmentRead)
async def update_department(
    department_id: int,
    data: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DepartmentRead:
    dept = await department_service.update_department(
        db, org_id=int(user["org_id"]), department_id=department_id, data=data,
    )
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")
    await record_action(
        db,
        event_type="department_updated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="department",
        entity_id=dept.id,
        payload_json={"name": dept.name},
    )
    return dept


@router.delete("/{department_id}", response_model=DepartmentRead)
async def deactivate_department(
    department_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN")),
) -> DepartmentRead:
    dept = await department_service.deactivate_department(
        db, org_id=int(user["org_id"]), department_id=department_id,
    )
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")
    await record_action(
        db,
        event_type="department_deactivated",
        actor_user_id=user["id"],
        organization_id=user["org_id"],
        entity_type="department",
        entity_id=dept.id,
        payload_json={"name": dept.name},
    )
    return dept
