"""Performance analytics: aggregate EmployeeWorkPattern data into metrics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_plan import DailyTaskPlan
from app.models.department import Department
from app.models.email import Email
from app.models.employee import Employee
from app.models.employee_work_pattern import EmployeeWorkPattern
from app.models.memory import TeamMember
from app.schemas.performance import (
    DepartmentOKRKeyResult,
    DepartmentOKRProgressRead,
    DepartmentPerformance,
    EmployeePerformance,
    OrgChartNode,
    OrgChartRead,
    OrgPerformance,
    PerformanceAlert,
    PerformanceTrend,
    SkillCoverage,
    SkillGap,
    SkillMatrixRead,
    WorkloadAction,
    WorkloadBalanceRead,
)


def _composite_score(avg_hours: float, avg_focus_ratio: float, avg_tasks: float) -> float:
    """Weighted composite: 30% hours normalised to 8h, 40% focus ratio, 30% task velocity normalised to 5/day."""
    hours_norm = min(avg_hours / 8.0, 1.0) if avg_hours > 0 else 0.0
    tasks_norm = min(avg_tasks / 5.0, 1.0) if avg_tasks > 0 else 0.0
    return round(hours_norm * 0.3 + avg_focus_ratio * 0.4 + tasks_norm * 0.3, 4)


def _parse_skills(raw: str | None) -> list[str]:
    if not raw:
        return []
    return sorted({part.strip().lower() for part in raw.split(",") if part.strip()})


class _MemberLoad(TypedDict):
    team_member_id: int
    name: str
    task_count: int
    high_priority_count: int
    workload_score: float
    has_plan: bool


async def get_employee_performance(
    db: AsyncSession,
    employee_id: int,
    org_id: int,
    days: int = 30,
) -> EmployeePerformance | None:
    cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).date()

    emp_row = (
        await db.execute(
            select(Employee).where(Employee.id == employee_id, Employee.organization_id == org_id)
        )
    ).scalar_one_or_none()
    if emp_row is None:
        return None

    agg = (
        await db.execute(
            select(
                func.count(EmployeeWorkPattern.id),
                func.avg(EmployeeWorkPattern.hours_logged),
                func.avg(EmployeeWorkPattern.focus_minutes),
                func.avg(EmployeeWorkPattern.active_minutes),
                func.sum(EmployeeWorkPattern.tasks_completed),
                func.sum(EmployeeWorkPattern.meetings_minutes),
            ).where(
                EmployeeWorkPattern.employee_id == employee_id,
                EmployeeWorkPattern.organization_id == org_id,
                EmployeeWorkPattern.work_date >= cutoff,
            )
        )
    ).one()
    count, avg_h, avg_focus, avg_active, total_tasks, total_meetings = agg
    count = int(count or 0)
    avg_h = float(avg_h or 0)
    avg_focus_val = float(avg_focus or 0)
    avg_active_val = float(avg_active or 1)
    total_tasks = int(total_tasks or 0)
    total_meetings = int(total_meetings or 0)

    focus_ratio = round(avg_focus_val / avg_active_val, 4) if avg_active_val > 0 else 0.0
    avg_tasks_day = round(total_tasks / max(count, 1), 2)
    score = _composite_score(avg_h, focus_ratio, avg_tasks_day)

    # Weekly trends
    trends: list[PerformanceTrend] = []
    weeks = max(1, days // 7)
    for w in range(weeks):
        w_start = cutoff + timedelta(weeks=w)
        w_end = w_start + timedelta(days=7)
        w_agg = (
            await db.execute(
                select(
                    func.avg(EmployeeWorkPattern.hours_logged),
                    func.avg(EmployeeWorkPattern.focus_minutes),
                    func.avg(EmployeeWorkPattern.active_minutes),
                    func.avg(EmployeeWorkPattern.tasks_completed),
                ).where(
                    EmployeeWorkPattern.employee_id == employee_id,
                    EmployeeWorkPattern.organization_id == org_id,
                    EmployeeWorkPattern.work_date >= w_start,
                    EmployeeWorkPattern.work_date < w_end,
                )
            )
        ).one()
        wh, wf, wa, wt = w_agg
        wh = float(wh or 0)
        wf_ratio = round(float(wf or 0) / float(wa or 1), 4) if float(wa or 0) > 0 else 0.0
        trends.append(PerformanceTrend(
            period_label=f"W{w + 1}",
            avg_hours=round(wh, 2),
            avg_focus_ratio=wf_ratio,
            avg_tasks=round(float(wt or 0), 2),
        ))

    return EmployeePerformance(
        employee_id=emp_row.id,
        employee_name=emp_row.name,
        department_id=emp_row.department_id,
        days_tracked=count,
        avg_hours=round(avg_h, 2),
        avg_focus_ratio=focus_ratio,
        avg_tasks_per_day=avg_tasks_day,
        total_tasks=total_tasks,
        total_meetings_minutes=total_meetings,
        composite_score=score,
        trends=trends,
    )


async def _bulk_employee_perf(
    db: AsyncSession,
    org_id: int,
    days: int,
    *,
    department_id: int | None = None,
    employee_ids: list[int] | None = None,
) -> list[EmployeePerformance]:
    """Bulk-fetch performance metrics for multiple employees in a single query."""
    cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).date()

    # Build employee filter
    emp_filter = [Employee.organization_id == org_id, Employee.is_active is True]
    if department_id is not None:
        emp_filter.append(Employee.department_id == department_id)
    if employee_ids is not None:
        emp_filter.append(Employee.id.in_(employee_ids))

    # Single aggregation query joining employees + work patterns
    agg_query = (
        select(
            Employee.id,
            Employee.name,
            Employee.department_id,
            func.count(EmployeeWorkPattern.id),
            func.avg(EmployeeWorkPattern.hours_logged),
            func.avg(EmployeeWorkPattern.focus_minutes),
            func.avg(EmployeeWorkPattern.active_minutes),
            func.sum(EmployeeWorkPattern.tasks_completed),
            func.sum(EmployeeWorkPattern.meetings_minutes),
        )
        .outerjoin(
            EmployeeWorkPattern,
            (EmployeeWorkPattern.employee_id == Employee.id)
            & (EmployeeWorkPattern.organization_id == org_id)
            & (EmployeeWorkPattern.work_date >= cutoff),
        )
        .where(*emp_filter)
        .group_by(Employee.id, Employee.name, Employee.department_id)
    )
    rows = (await db.execute(agg_query)).all()

    results: list[EmployeePerformance] = []
    for row in rows:
        emp_id, emp_name, dept_id, count, avg_h, avg_focus, avg_active, total_tasks, total_meetings = row
        count = int(count or 0)
        avg_h = float(avg_h or 0)
        avg_focus_val = float(avg_focus or 0)
        avg_active_val = float(avg_active or 1)
        total_tasks = int(total_tasks or 0)
        total_meetings = int(total_meetings or 0)

        focus_ratio = round(avg_focus_val / avg_active_val, 4) if avg_active_val > 0 else 0.0
        avg_tasks_day = round(total_tasks / max(count, 1), 2)
        score = _composite_score(avg_h, focus_ratio, avg_tasks_day)

        results.append(EmployeePerformance(
            employee_id=emp_id,
            employee_name=emp_name,
            department_id=dept_id,
            days_tracked=count,
            avg_hours=round(avg_h, 2),
            avg_focus_ratio=focus_ratio,
            avg_tasks_per_day=avg_tasks_day,
            total_tasks=total_tasks,
            total_meetings_minutes=total_meetings,
            composite_score=score,
            trends=[],
        ))

    return results


async def get_department_performance(
    db: AsyncSession,
    department_id: int,
    org_id: int,
    days: int = 30,
) -> DepartmentPerformance | None:
    dept = (
        await db.execute(
            select(Department).where(Department.id == department_id, Department.organization_id == org_id)
        )
    ).scalar_one_or_none()
    if dept is None:
        return None

    emp_perfs = await _bulk_employee_perf(db, org_id, days, department_id=department_id)

    emp_count = len(emp_perfs)
    avg_h = round(sum(e.avg_hours for e in emp_perfs) / max(emp_count, 1), 2)
    avg_fr = round(sum(e.avg_focus_ratio for e in emp_perfs) / max(emp_count, 1), 4)
    avg_t = round(sum(e.avg_tasks_per_day for e in emp_perfs) / max(emp_count, 1), 2)
    total_t = sum(e.total_tasks for e in emp_perfs)

    top = sorted(emp_perfs, key=lambda e: e.composite_score, reverse=True)[:5]

    return DepartmentPerformance(
        department_id=dept.id,
        department_name=dept.name,
        employee_count=emp_count,
        avg_hours=avg_h,
        avg_focus_ratio=avg_fr,
        avg_tasks_per_day=avg_t,
        total_tasks=total_t,
        top_performers=top,
    )


async def get_org_performance(
    db: AsyncSession,
    org_id: int,
    days: int = 30,
) -> OrgPerformance:
    cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).date()

    emp_count = int(
        (
            await db.execute(
                select(func.count(Employee.id)).where(
                    Employee.organization_id == org_id, Employee.is_active is True
                )
            )
        ).scalar_one() or 0
    )

    dept_count = int(
        (
            await db.execute(
                select(func.count(Department.id)).where(
                    Department.organization_id == org_id, Department.is_active is True
                )
            )
        ).scalar_one() or 0
    )

    agg = (
        await db.execute(
            select(
                func.avg(EmployeeWorkPattern.hours_logged),
                func.avg(EmployeeWorkPattern.focus_minutes),
                func.avg(EmployeeWorkPattern.active_minutes),
                func.avg(EmployeeWorkPattern.tasks_completed),
            ).where(
                EmployeeWorkPattern.organization_id == org_id,
                EmployeeWorkPattern.work_date >= cutoff,
            )
        )
    ).one()
    avg_h = float(agg[0] or 0)
    avg_focus = float(agg[1] or 0)
    avg_active = float(agg[2] or 1)
    avg_tasks = float(agg[3] or 0)
    focus_ratio = round(avg_focus / avg_active, 4) if avg_active > 0 else 0.0

    # Departmental breakdown — single bulk query
    dept_agg_query = (
        select(
            Department.id,
            Department.name,
            func.count(func.distinct(Employee.id)),
            func.avg(EmployeeWorkPattern.hours_logged),
            func.avg(EmployeeWorkPattern.focus_minutes),
            func.avg(EmployeeWorkPattern.active_minutes),
            func.avg(EmployeeWorkPattern.tasks_completed),
            func.sum(EmployeeWorkPattern.tasks_completed),
        )
        .outerjoin(Employee, (Employee.department_id == Department.id) & (Employee.is_active is True))
        .outerjoin(
            EmployeeWorkPattern,
            (EmployeeWorkPattern.employee_id == Employee.id)
            & (EmployeeWorkPattern.organization_id == org_id)
            & (EmployeeWorkPattern.work_date >= cutoff),
        )
        .where(Department.organization_id == org_id, Department.is_active is True)
        .group_by(Department.id, Department.name)
        .order_by(Department.name)
    )
    dept_rows = (await db.execute(dept_agg_query)).all()

    dept_perfs: list[DepartmentPerformance] = []
    for row in dept_rows:
        d_id, d_name, d_emp_count, d_avg_h, d_avg_f, d_avg_a, d_avg_t, d_total_t = row
        d_emp_count = int(d_emp_count or 0)
        d_avg_h = float(d_avg_h or 0)
        d_avg_a_val = float(d_avg_a or 1)
        d_focus_ratio = round(float(d_avg_f or 0) / d_avg_a_val, 4) if d_avg_a_val > 0 else 0.0
        dept_perfs.append(DepartmentPerformance(
            department_id=d_id,
            department_name=d_name,
            employee_count=d_emp_count,
            avg_hours=round(d_avg_h, 2),
            avg_focus_ratio=d_focus_ratio,
            avg_tasks_per_day=round(float(d_avg_t or 0), 2),
            total_tasks=int(d_total_t or 0),
            top_performers=[],
        ))

    return OrgPerformance(
        organization_id=org_id,
        total_employees=emp_count,
        total_departments=dept_count,
        avg_hours=round(avg_h, 2),
        avg_focus_ratio=focus_ratio,
        avg_tasks_per_day=round(avg_tasks, 2),
        departments=dept_perfs,
    )


async def get_top_performers(
    db: AsyncSession,
    org_id: int,
    days: int = 30,
    limit: int = 10,
) -> list[EmployeePerformance]:
    perfs = await _bulk_employee_perf(db, org_id, days)
    perfs = [p for p in perfs if p.days_tracked > 0]
    perfs.sort(key=lambda e: e.composite_score, reverse=True)
    return perfs[:limit]


async def get_performance_alerts(
    db: AsyncSession,
    org_id: int,
    days: int = 30,
    threshold: float = 0.3,
) -> list[PerformanceAlert]:
    perfs = await _bulk_employee_perf(db, org_id, days)

    alerts: list[PerformanceAlert] = []
    for ep in perfs:
        if ep.days_tracked > 0 and ep.composite_score < threshold:
            reason = "Low composite performance score"
            if ep.avg_hours < 4:
                reason = "Very low average working hours"
            elif ep.avg_focus_ratio < 0.2:
                reason = "Very low focus ratio"
            elif ep.avg_tasks_per_day < 1:
                reason = "Very low task completion rate"
            alerts.append(PerformanceAlert(
                employee_id=ep.employee_id,
                employee_name=ep.employee_name,
                department_id=ep.department_id,
                composite_score=ep.composite_score,
                alert_reason=reason,
            ))

    return alerts


async def get_org_chart(
    db: AsyncSession,
    org_id: int,
) -> OrgChartRead:
    rows = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.organization_id == org_id,
                TeamMember.is_active.is_(True),
            )
        )
    ).scalars().all()
    by_id = {int(item.id): item for item in rows}
    direct_reports_count: dict[int, int] = {int(item.id): 0 for item in rows}
    for item in rows:
        manager_id = int(item.reports_to_id) if item.reports_to_id else None
        if manager_id in direct_reports_count:
            direct_reports_count[manager_id] += 1

    nodes: list[OrgChartNode] = []
    roots: list[int] = []
    for item in rows:
        item_id = int(item.id)
        manager_id = int(item.reports_to_id) if item.reports_to_id else None
        if manager_id is None or manager_id not in by_id:
            roots.append(item_id)
        nodes.append(
            OrgChartNode(
                team_member_id=item_id,
                name=item.name,
                role_title=item.role_title,
                team=item.team,
                reports_to_id=manager_id,
                direct_reports_count=direct_reports_count[item_id],
                ai_level=int(item.ai_level or 0),
                skills=_parse_skills(item.skills),
            )
        )

    nodes.sort(key=lambda n: (n.reports_to_id or 0, n.name.lower()))
    roots.sort()
    return OrgChartRead(
        organization_id=org_id,
        roots=roots,
        nodes=nodes,
    )


async def get_workload_balance(
    db: AsyncSession,
    org_id: int,
    *,
    for_date: date,
) -> WorkloadBalanceRead:
    members = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.organization_id == org_id,
                TeamMember.is_active.is_(True),
            )
        )
    ).scalars().all()
    if not members:
        return WorkloadBalanceRead(
            organization_id=org_id,
            for_date=for_date,
            average_task_load=0.0,
            overloaded_count=0,
            underloaded_count=0,
            actions=[],
            by_member=[],
        )

    member_ids = [int(m.id) for m in members]
    plans = (
        await db.execute(
            select(DailyTaskPlan).where(
                DailyTaskPlan.organization_id == org_id,
                DailyTaskPlan.date == for_date,
                DailyTaskPlan.team_member_id.in_(member_ids),
            )
        )
    ).scalars().all()
    plan_by_member = {int(plan.team_member_id): plan for plan in plans}

    by_member: list[_MemberLoad] = []
    for member in members:
        plan = plan_by_member.get(int(member.id))
        tasks = plan.tasks_json if plan else []
        task_count = len(tasks)
        high_priority = sum(
            1 for task in tasks
            if str(task.get("priority", "")).strip().lower() == "high"
        )
        workload_score = round(task_count + (high_priority * 0.75), 2)
        by_member.append(
            {
                "team_member_id": int(member.id),
                "name": member.name,
                "task_count": task_count,
                "high_priority_count": high_priority,
                "workload_score": workload_score,
                "has_plan": plan is not None,
            }
        )

    avg_load = round(
        sum(item["workload_score"] for item in by_member) / max(len(by_member), 1),
        2,
    )
    overloaded = sorted(
        [item for item in by_member if item["workload_score"] >= avg_load + 1.5],
        key=lambda item: item["workload_score"],
        reverse=True,
    )
    underloaded = sorted(
        [item for item in by_member if item["workload_score"] <= max(0.0, avg_load - 1.0)],
        key=lambda item: item["workload_score"],
    )

    actions: list[WorkloadAction] = []
    for source, target in zip(overloaded, underloaded, strict=False):
        delta = source["workload_score"] - target["workload_score"]
        move_count = max(1, int(delta // 1.5))
        actions.append(
            WorkloadAction(
                from_member_id=source["team_member_id"],
                from_member_name=source["name"],
                to_member_id=target["team_member_id"],
                to_member_name=target["name"],
                suggested_task_moves=move_count,
                reason=(
                    f"Shift {move_count} task(s): {source['name']} is overloaded "
                    f"({source['workload_score']}) while {target['name']} is underloaded "
                    f"({target['workload_score']})."
                ),
            )
        )

    return WorkloadBalanceRead(
        organization_id=org_id,
        for_date=for_date,
        average_task_load=avg_load,
        overloaded_count=len(overloaded),
        underloaded_count=len(underloaded),
        actions=actions,
        by_member=[dict(item) for item in by_member],
    )


async def get_skill_matrix(
    db: AsyncSession,
    org_id: int,
    *,
    required_skills: list[str],
) -> SkillMatrixRead:
    members = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.organization_id == org_id,
                TeamMember.is_active.is_(True),
            )
        )
    ).scalars().all()

    normalized_required = sorted(
        {
            skill.strip().lower()
            for skill in required_skills
            if skill.strip()
        }
    )
    if not normalized_required:
        normalized_required = ["python", "sql", "communication", "ai"]

    coverage_map: dict[str, list[str]] = {skill: [] for skill in normalized_required}
    member_gaps: list[SkillGap] = []

    for member in members:
        skill_set = set(_parse_skills(member.skills))
        for skill in normalized_required:
            if skill in skill_set:
                coverage_map[skill].append(member.name)
        missing = [skill for skill in normalized_required if skill not in skill_set]
        if missing:
            member_gaps.append(
                SkillGap(
                    team_member_id=int(member.id),
                    team_member_name=member.name,
                    missing_skills=missing,
                )
            )

    coverage = [
        SkillCoverage(
            skill=skill,
            members_count=len(names),
            members=sorted(names),
        )
        for skill, names in coverage_map.items()
    ]
    org_missing = [item.skill for item in coverage if item.members_count == 0]

    return SkillMatrixRead(
        organization_id=org_id,
        required_skills=normalized_required,
        coverage=coverage,
        member_gaps=member_gaps,
        org_missing_skills=org_missing,
    )


async def get_department_okr_progress(
    db: AsyncSession,
    org_id: int,
    *,
    department_id: int,
    from_date: date,
    to_date: date,
) -> DepartmentOKRProgressRead | None:
    dept = (
        await db.execute(
            select(Department).where(
                Department.organization_id == org_id,
                Department.id == department_id,
            )
        )
    ).scalar_one_or_none()
    if dept is None:
        return None

    employees = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == org_id,
                Employee.department_id == department_id,
                Employee.is_active.is_(True),
            )
        )
    ).scalars().all()
    employee_ids = [int(emp.id) for emp in employees]
    if not employee_ids:
        return DepartmentOKRProgressRead(
            organization_id=org_id,
            department_id=department_id,
            department_name=dept.name,
            from_date=from_date,
            to_date=to_date,
            overall_progress_percent=0,
            signals={
                "employees": 0,
                "tasks_completed": 0,
                "meetings_minutes": 0,
                "avg_focus_ratio": 0.0,
                "org_unread_emails": 0,
            },
            key_results=[],
        )

    patterns = (
        await db.execute(
            select(EmployeeWorkPattern).where(
                EmployeeWorkPattern.organization_id == org_id,
                EmployeeWorkPattern.employee_id.in_(employee_ids),
                EmployeeWorkPattern.work_date >= from_date,
                EmployeeWorkPattern.work_date <= to_date,
            )
        )
    ).scalars().all()
    total_tasks = sum(int(item.tasks_completed or 0) for item in patterns)
    total_meetings = sum(int(item.meetings_minutes or 0) for item in patterns)
    total_focus = sum(int(item.focus_minutes or 0) for item in patterns)
    total_active = sum(int(item.active_minutes or 0) for item in patterns)
    focus_ratio = round((total_focus / total_active), 4) if total_active > 0 else 0.0

    unread_emails = int(
        (
            await db.execute(
                select(func.count(Email.id)).where(
                    Email.organization_id == org_id,
                    Email.is_read.is_(False),
                )
            )
        ).scalar_one() or 0
    )

    # Signal-derived KR set, auto-updated from tasks/emails/meetings activity.
    tasks_target = max(1, len(employee_ids) * 20)
    focus_target = 0.45
    unread_target = max(5, len(employee_ids) * 10)

    kr_tasks = min(100, int(round((total_tasks / tasks_target) * 100)))
    kr_focus = min(100, int(round((focus_ratio / focus_target) * 100))) if focus_target > 0 else 0
    kr_email = min(100, int(round((unread_target / max(unread_emails, 1)) * 100)))
    overall = int(round((kr_tasks + kr_focus + kr_email) / 3))

    return DepartmentOKRProgressRead(
        organization_id=org_id,
        department_id=department_id,
        department_name=dept.name,
        from_date=from_date,
        to_date=to_date,
        overall_progress_percent=min(100, max(0, overall)),
        signals={
            "employees": len(employee_ids),
            "tasks_completed": total_tasks,
            "meetings_minutes": total_meetings,
            "avg_focus_ratio": focus_ratio,
            "org_unread_emails": unread_emails,
        },
        key_results=[
            DepartmentOKRKeyResult(
                key_result="Weekly task delivery",
                target=f">= {tasks_target} tasks completed",
                actual=f"{total_tasks} tasks completed",
                progress_percent=kr_tasks,
            ),
            DepartmentOKRKeyResult(
                key_result="Deep work focus ratio",
                target=f">= {focus_target:.2f}",
                actual=f"{focus_ratio:.2f}",
                progress_percent=kr_focus,
            ),
            DepartmentOKRKeyResult(
                key_result="Inbox hygiene (org-level proxy)",
                target=f"<= {unread_target} unread emails",
                actual=f"{unread_emails} unread emails",
                progress_percent=kr_email,
            ),
        ],
    )
