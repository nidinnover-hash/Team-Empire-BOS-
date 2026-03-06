from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.employee_work_pattern import EmployeeWorkPattern
from app.schemas.brain_context import BrainContext, EmployeeContext, OrgContext
from app.services import clone_control
from app.services import organization as organization_service

_ROLE_CAPABILITIES: dict[str, list[str]] = {
    "CEO": ["org:read", "org:write", "policy:write", "employee:write", "approval:override"],
    "ADMIN": ["org:read", "policy:write", "employee:write"],
    "MANAGER": ["org:read", "employee:read", "task:write"],
    "STAFF": ["org:read", "task:read"],
}


async def _employee_context(
    db: AsyncSession,
    *,
    organization_id: int,
    employee_id: int,
) -> EmployeeContext | None:
    row = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id,
                Employee.id == employee_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    profile = await clone_control.get_clone_profile(
        db,
        organization_id=organization_id,
        employee_id=employee_id,
    )
    profile_payload: dict[str, object] = {}
    if profile is not None:
        profile_payload = clone_control.profile_to_payload(profile)

    since = date.today() - timedelta(days=6)
    patterns = (
        await db.execute(
            select(EmployeeWorkPattern).where(
                EmployeeWorkPattern.organization_id == organization_id,
                EmployeeWorkPattern.employee_id == employee_id,
                EmployeeWorkPattern.work_date >= since,
            )
        )
    ).scalars().all()
    total_days = max(len(patterns), 1)
    hours = sum(float(item.hours_logged or 0.0) for item in patterns)
    focus = sum(int(item.focus_minutes or 0) for item in patterns)
    active = sum(int(item.active_minutes or 0) for item in patterns)
    tasks = sum(int(item.tasks_completed or 0) for item in patterns)
    work_pattern: dict[str, object] = {
        "window_days": 7,
        "avg_hours_logged": round(hours / total_days, 2),
        "avg_focus_ratio": round((focus / active), 4) if active > 0 else 0.0,
        "tasks_completed": tasks,
    }

    return EmployeeContext(
        employee_id=int(row.id),
        name=row.name,
        job_title=row.job_title,
        department_id=row.department_id,
        employment_status=row.employment_status,
        profile=profile_payload,
        recent_work_pattern=work_pattern,
    )


async def build_brain_context(
    db: AsyncSession,
    *,
    organization_id: int,
    actor_user_id: int | None,
    actor_role: str | None,
    request_purpose: str = "professional",
    employee_id: int | None = None,
    capabilities: list[str] | None = None,
) -> BrainContext:
    org = await organization_service.get_organization_by_id(db, organization_id)
    if org is None:
        raise ValueError("Organization not found")
    policy = await organization_service.get_policy_config(db, organization_id)
    role_key = (actor_role or "").upper()
    role_capabilities = _ROLE_CAPABILITIES.get(role_key, ["org:read"])
    merged_capabilities = list(dict.fromkeys([*(capabilities or []), *role_capabilities]))

    employee = None
    if employee_id is not None:
        employee = await _employee_context(
            db,
            organization_id=organization_id,
            employee_id=employee_id,
        )

    return BrainContext(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        request_purpose=request_purpose,
        capabilities=merged_capabilities,
        org=OrgContext(
            id=int(org.id),
            slug=org.slug,
            name=org.name,
            country_code=org.country_code,
            branch_label=org.branch_label,
            parent_organization_id=org.parent_organization_id,
            policy=policy,
        ),
        employee=employee,
    )


__all__ = ["build_brain_context"]
