from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.schemas.department import DepartmentCreate, DepartmentUpdate


async def list_departments(
    db: AsyncSession,
    org_id: int,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> list[Department]:
    query = select(Department).where(Department.organization_id == org_id)
    if active_only:
        query = query.where(Department.is_active.is_(True))
    query = query.order_by(Department.name).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_department(
    db: AsyncSession,
    org_id: int,
    department_id: int,
) -> Department | None:
    result = await db.execute(
        select(Department).where(
            Department.organization_id == org_id,
            Department.id == department_id,
        )
    )
    return result.scalar_one_or_none()


async def create_department(
    db: AsyncSession,
    org_id: int,
    data: DepartmentCreate,
) -> Department:
    dept = Department(
        organization_id=org_id,
        name=data.name,
        code=data.code,
        parent_department_id=data.parent_department_id,
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


async def update_department(
    db: AsyncSession,
    org_id: int,
    department_id: int,
    data: DepartmentUpdate,
) -> Department | None:
    dept = await get_department(db, org_id, department_id)
    if dept is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dept, field, value)
    dept.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(dept)
    return dept


async def deactivate_department(
    db: AsyncSession,
    org_id: int,
    department_id: int,
) -> Department | None:
    dept = await get_department(db, org_id, department_id)
    if dept is None:
        return None
    dept.is_active = False
    dept.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(dept)
    return dept
