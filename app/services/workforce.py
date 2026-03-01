from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.employee import Employee
from app.models.employee_lifecycle import EmployeeLifecycleEvent
from app.models.employee_work_pattern import EmployeeWorkPattern
from app.schemas.workforce import (
    DepartmentCreate,
    DepartmentUpdate,
    EmployeeOffboardRequest,
    EmployeeOnboardRequest,
    WorkPatternUpsert,
)


async def create_department(
    db: AsyncSession,
    organization_id: int,
    data: DepartmentCreate,
) -> Department:
    row = Department(
        organization_id=organization_id,
        parent_department_id=data.parent_department_id,
        name=data.name.strip(),
        code=data.code.strip().upper(),
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_departments(db: AsyncSession, organization_id: int) -> list[Department]:
    result = await db.execute(
        select(Department)
        .where(Department.organization_id == organization_id)
        .order_by(Department.name.asc())
    )
    return list(result.scalars().all())


async def get_department(
    db: AsyncSession,
    organization_id: int,
    department_id: int,
) -> Department | None:
    row = await db.execute(
        select(Department).where(
            Department.organization_id == organization_id,
            Department.id == department_id,
        )
    )
    return row.scalar_one_or_none()


async def update_department(
    db: AsyncSession,
    organization_id: int,
    department_id: int,
    data: DepartmentUpdate,
) -> Department | None:
    row = await get_department(db, organization_id, department_id)
    if row is None:
        return None
    payload = data.model_dump(exclude_unset=True)
    name = payload.get("name")
    if name:
        row.name = str(name).strip()
    code = payload.get("code")
    if code:
        row.code = str(code).strip().upper()
    if "parent_department_id" in payload:
        row.parent_department_id = payload["parent_department_id"]
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
    await db.commit()
    await db.refresh(row)
    return row


async def onboard_employee(
    db: AsyncSession,
    organization_id: int,
    actor_user_id: int,
    data: EmployeeOnboardRequest,
) -> Employee:
    existing = await db.execute(
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.email == data.email.strip(),
        )
    )
    row = existing.scalar_one_or_none()
    normalized_role = (data.role or "").strip()
    if row is None:
        row = Employee(
            organization_id=organization_id,
            name=data.name.strip(),
            role=normalized_role,
            email=data.email.strip(),
            department_id=data.department_id,
            github_username=(data.github_username or "").strip() or None,
            clickup_user_id=(data.clickup_user_id or "").strip() or None,
            employment_status="active",
            hired_at=data.hired_at or datetime.now(UTC),
            offboarded_at=None,
            is_active=True,
        )
        db.add(row)
        await db.flush()
    else:
        row.name = data.name.strip()
        row.role = normalized_role
        row.department_id = data.department_id
        row.github_username = (data.github_username or "").strip() or None
        row.clickup_user_id = (data.clickup_user_id or "").strip() or None
        row.employment_status = "active"
        row.hired_at = data.hired_at or row.hired_at or datetime.now(UTC)
        row.offboarded_at = None
        row.is_active = True

    db.add(
        EmployeeLifecycleEvent(
            organization_id=organization_id,
            employee_id=row.id,
            event_type="onboard",
            effective_date=(data.hired_at.date() if data.hired_at else date.today()),
            checklist_json=json.dumps(data.checklist or []),
            notes=data.notes,
            actor_user_id=actor_user_id,
        )
    )
    await db.commit()
    await db.refresh(row)
    return row


async def offboard_employee(
    db: AsyncSession,
    organization_id: int,
    actor_user_id: int,
    employee_id: int,
    data: EmployeeOffboardRequest,
) -> Employee | None:
    row_result = await db.execute(
        select(Employee).where(
            Employee.organization_id == organization_id,
            Employee.id == employee_id,
        )
    )
    row = row_result.scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(UTC)
    row.employment_status = "offboarded"
    row.is_active = False
    row.offboarded_at = now
    db.add(
        EmployeeLifecycleEvent(
            organization_id=organization_id,
            employee_id=employee_id,
            event_type="offboard",
            effective_date=data.effective_date or date.today(),
            checklist_json=json.dumps(data.checklist or []),
            notes=data.notes,
            actor_user_id=actor_user_id,
        )
    )
    await db.commit()
    await db.refresh(row)
    return row


async def list_lifecycle_events(
    db: AsyncSession,
    organization_id: int,
    employee_id: int,
) -> list[EmployeeLifecycleEvent]:
    rows = await db.execute(
        select(EmployeeLifecycleEvent)
        .where(
            EmployeeLifecycleEvent.organization_id == organization_id,
            EmployeeLifecycleEvent.employee_id == employee_id,
        )
        .order_by(EmployeeLifecycleEvent.created_at.desc())
    )
    return list(rows.scalars().all())


async def upsert_work_patterns(
    db: AsyncSession,
    organization_id: int,
    items: list[WorkPatternUpsert],
) -> list[EmployeeWorkPattern]:
    saved: list[EmployeeWorkPattern] = []
    for item in items:
        existing = await db.execute(
            select(EmployeeWorkPattern).where(
                EmployeeWorkPattern.organization_id == organization_id,
                EmployeeWorkPattern.employee_id == item.employee_id,
                EmployeeWorkPattern.work_date == item.work_date,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            row = EmployeeWorkPattern(
                organization_id=organization_id,
                employee_id=item.employee_id,
                work_date=item.work_date,
            )
            db.add(row)
            await db.flush()
        row.hours_logged = float(item.hours_logged)
        row.active_minutes = int(item.active_minutes)
        row.focus_minutes = int(item.focus_minutes)
        row.meetings_minutes = int(item.meetings_minutes)
        row.tasks_completed = int(item.tasks_completed)
        row.source = item.source
        saved.append(row)
    await db.commit()
    for row in saved:
        await db.refresh(row)
    return saved


async def work_pattern_analytics(
    db: AsyncSession,
    organization_id: int,
    from_date: date,
    to_date: date,
    department_id: int | None = None,
) -> list[dict[str, object]]:
    def _activity_score(row: dict[str, object]) -> float:
        value = row.get("activity_score")
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        return 0.0

    employees_query = select(Employee).where(Employee.organization_id == organization_id)
    if department_id is not None:
        employees_query = employees_query.where(Employee.department_id == department_id)
    employees = list((await db.execute(employees_query)).scalars().all())
    if not employees:
        return []

    employee_ids = [int(e.id) for e in employees]
    rows = (
        await db.execute(
            select(EmployeeWorkPattern).where(
                EmployeeWorkPattern.organization_id == organization_id,
                EmployeeWorkPattern.employee_id.in_(employee_ids),
                EmployeeWorkPattern.work_date >= from_date,
                EmployeeWorkPattern.work_date <= to_date,
            )
        )
    ).scalars().all()
    by_employee: dict[int, list[EmployeeWorkPattern]] = {}
    for row in rows:
        by_employee.setdefault(int(row.employee_id), []).append(row)

    result: list[dict[str, object]] = []
    for emp in employees:
        patterns = by_employee.get(int(emp.id), [])
        total_days = max(len(patterns), 1)
        hours = sum(float(p.hours_logged or 0.0) for p in patterns)
        focus = sum(int(p.focus_minutes or 0) for p in patterns)
        active = sum(int(p.active_minutes or 0) for p in patterns)
        tasks = sum(int(p.tasks_completed or 0) for p in patterns)
        avg_hours = hours / total_days
        focus_ratio = (focus / active) if active > 0 else 0.0
        activity_score = min(100.0, max(0.0, (avg_hours * 8.0) + (focus_ratio * 40.0) + (tasks * 2.0)))
        result.append(
            {
                "employee_id": int(emp.id),
                "employee_name": emp.name,
                "department_id": emp.department_id,
                "avg_hours_logged": round(avg_hours, 2),
                "avg_focus_ratio": round(focus_ratio, 4),
                "total_tasks_completed": tasks,
                "activity_score": round(activity_score, 2),
            }
        )
    result.sort(key=_activity_score, reverse=True)
    return result
