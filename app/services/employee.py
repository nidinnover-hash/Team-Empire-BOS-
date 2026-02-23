from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.schemas.ops import EmployeeCreate, EmployeeUpdate


async def create_or_update_employee(
    db: AsyncSession,
    org_id: int,
    data: EmployeeCreate,
) -> Employee:
    """Create employee or update if email already exists for this org."""
    result = await db.execute(
        select(Employee).where(
            Employee.organization_id == org_id,
            Employee.email == data.email,
        )
    )
    existing = cast(Employee | None, result.scalar_one_or_none())

    if existing:
        existing.name = data.name
        existing.role = data.role
        existing.github_username = data.github_username
        existing.clickup_user_id = data.clickup_user_id
        existing.is_active = data.is_active
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    emp = Employee(
        organization_id=org_id,
        name=data.name,
        role=data.role,
        email=data.email,
        github_username=data.github_username,
        clickup_user_id=data.clickup_user_id,
        is_active=data.is_active,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    return emp


async def list_employees(
    db: AsyncSession,
    org_id: int,
    active_only: bool = True,
) -> list[Employee]:
    query = select(Employee).where(Employee.organization_id == org_id)
    if active_only:
        query = query.where(Employee.is_active == True)  # noqa: E712
    query = query.order_by(Employee.name)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_employee(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
) -> Employee | None:
    result = await db.execute(
        select(Employee).where(
            Employee.organization_id == org_id,
            Employee.id == employee_id,
        )
    )
    return cast(Employee | None, result.scalar_one_or_none())


async def update_employee(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
    data: EmployeeUpdate,
) -> Employee | None:
    emp = await get_employee(db, org_id, employee_id)
    if emp is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(emp, field, value)
    emp.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(emp)
    return emp
