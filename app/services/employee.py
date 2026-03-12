import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.schemas.ops import EmployeeCreate, EmployeeUpdate

logger = logging.getLogger(__name__)


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
    existing = result.scalar_one_or_none()

    if existing:
        existing.name = data.name
        existing.job_title = data.job_title  # type: ignore[assignment]  # SQLAlchemy mapped col
        existing.department_id = data.department_id
        existing.github_username = data.github_username
        existing.clickup_user_id = data.clickup_user_id
        existing.employment_status = data.employment_status
        existing.is_active = data.is_active
        existing.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(existing)
        return existing

    emp = Employee(
        organization_id=org_id,
        name=data.name,
        job_title=data.job_title,
        email=data.email,
        department_id=data.department_id,
        github_username=data.github_username,
        clickup_user_id=data.clickup_user_id,
        employment_status=data.employment_status,
        is_active=data.is_active,
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)
    logger.info("employee created id=%d org=%d", emp.id, org_id)
    return emp


async def list_employees(
    db: AsyncSession,
    org_id: int,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> list[Employee]:
    query = select(Employee).where(Employee.organization_id == org_id)
    if active_only:
        query = query.where(Employee.is_active is True)
    query = query.order_by(Employee.name).offset(skip).limit(limit)
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
    return result.scalar_one_or_none()


async def update_employee(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
    data: EmployeeUpdate,
) -> Employee | None:
    emp = await get_employee(db, org_id, employee_id)
    if emp is None:
        return None

    _ALLOWED_FIELDS = {
        "name", "job_title", "email", "department_id",
        "github_username", "clickup_user_id", "employment_status", "is_active",
    }
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in _ALLOWED_FIELDS:
            setattr(emp, field, value)
    emp.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(emp)
    logger.info("employee updated id=%d org=%d", employee_id, org_id)
    return emp


async def list_by_department(
    db: AsyncSession,
    org_id: int,
    department_id: int,
    active_only: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> list[Employee]:
    query = select(Employee).where(
        Employee.organization_id == org_id,
        Employee.department_id == department_id,
    )
    if active_only:
        query = query.where(Employee.is_active is True)
    query = query.order_by(Employee.name).offset(offset).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def offboard_employee(
    db: AsyncSession,
    org_id: int,
    employee_id: int,
) -> Employee | None:
    emp = await get_employee(db, org_id, employee_id)
    if emp is None:
        return None
    emp.is_active = False
    emp.employment_status = "offboarded"
    emp.offboarded_at = datetime.now(UTC)
    emp.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(emp)
    logger.info("employee offboarded id=%d org=%d", employee_id, org_id)
    return emp
