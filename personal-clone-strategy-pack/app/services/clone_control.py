from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.approval import Approval
from app.models.clone_control import (
    CloneLearningFeedback,
    EmployeeCloneProfile,
    EmployeeIdentityMap,
    RoleTrainingPlan,
)
from app.models.clone_performance import ClonePerformanceWeekly
from app.models.email import Email
from app.models.employee import Employee
from app.models.ops_metrics import CodeMetricWeekly, CommsMetricWeekly, TaskMetricWeekly


async def upsert_identity_map(
    db: AsyncSession,
    *,
    organization_id: int,
    employee_id: int,
    work_email: str | None,
    github_login: str | None,
    clickup_user_id: str | None,
    slack_user_id: str | None,
) -> EmployeeIdentityMap:
    row = (
        await db.execute(
            select(EmployeeIdentityMap).where(
                EmployeeIdentityMap.organization_id == organization_id,
                EmployeeIdentityMap.employee_id == employee_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = EmployeeIdentityMap(
            organization_id=organization_id,
            employee_id=employee_id,
        )
    row.work_email = (work_email or None)
    row.github_login = (github_login or None)
    row.clickup_user_id = (clickup_user_id or None)
    row.slack_user_id = (slack_user_id or None)
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return cast(EmployeeIdentityMap, row)


async def list_identity_maps(db: AsyncSession, *, organization_id: int) -> list[EmployeeIdentityMap]:
    rows = (
        await db.execute(
            select(EmployeeIdentityMap).where(EmployeeIdentityMap.organization_id == organization_id)
            .order_by(EmployeeIdentityMap.employee_id.asc())
        )
    ).scalars().all()
    return list(rows)


async def upsert_clone_profile(
    db: AsyncSession,
    *,
    organization_id: int,
    employee_id: int,
    strengths: list[str],
    weak_zones: list[str],
    preferred_task_types: list[str],
) -> EmployeeCloneProfile:
    row = (
        await db.execute(
            select(EmployeeCloneProfile).where(
                EmployeeCloneProfile.organization_id == organization_id,
                EmployeeCloneProfile.employee_id == employee_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = EmployeeCloneProfile(
            organization_id=organization_id,
            employee_id=employee_id,
        )
    row.strengths_json = json.dumps(strengths[:20])
    row.weak_zones_json = json.dumps(weak_zones[:20])
    row.preferred_task_types_json = json.dumps(preferred_task_types[:20])
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return cast(EmployeeCloneProfile, row)


def profile_to_payload(row: EmployeeCloneProfile) -> dict[str, object]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "employee_id": row.employee_id,
        "strengths": json.loads(row.strengths_json or "[]"),
        "weak_zones": json.loads(row.weak_zones_json or "[]"),
        "preferred_task_types": json.loads(row.preferred_task_types_json or "[]"),
        "updated_at": row.updated_at,
    }


async def get_clone_profile(
    db: AsyncSession,
    *,
    organization_id: int,
    employee_id: int,
) -> EmployeeCloneProfile | None:
    row = (
        await db.execute(
            select(EmployeeCloneProfile).where(
                EmployeeCloneProfile.organization_id == organization_id,
                EmployeeCloneProfile.employee_id == employee_id,
            )
        )
    ).scalar_one_or_none()
    return cast(EmployeeCloneProfile | None, row)


async def record_feedback(
    db: AsyncSession,
    *,
    organization_id: int,
    employee_id: int,
    source_type: str,
    source_id: int | None,
    outcome_score: float,
    notes: str | None,
    created_by: int | None,
) -> CloneLearningFeedback:
    row = CloneLearningFeedback(
        organization_id=organization_id,
        employee_id=employee_id,
        source_type=source_type,
        source_id=source_id,
        outcome_score=outcome_score,
        notes=notes,
        created_by=created_by,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return cast(CloneLearningFeedback, row)


async def feedback_adjustment_for_employee(
    db: AsyncSession,
    *,
    organization_id: int,
    employee_id: int,
    lookback_days: int = 30,
) -> float:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))
    avg_score = (
        await db.execute(
            select(func.avg(CloneLearningFeedback.outcome_score)).where(
                CloneLearningFeedback.organization_id == organization_id,
                CloneLearningFeedback.employee_id == employee_id,
                CloneLearningFeedback.created_at >= cutoff,
            )
        )
    ).scalar_one_or_none()
    if avg_score is None:
        return 0.0
    score = float(avg_score)
    return (score - 0.5) * 20.0  # maps 0..1 into -10..+10


async def generate_role_training_plans(
    db: AsyncSession,
    *,
    organization_id: int,
    week_start_date: date,
) -> dict[str, int]:
    scores = (
        await db.execute(
            select(ClonePerformanceWeekly).where(
                ClonePerformanceWeekly.organization_id == organization_id,
                ClonePerformanceWeekly.week_start_date == week_start_date,
            )
        )
    ).scalars().all()
    employees = (
        await db.execute(
            select(Employee).where(Employee.organization_id == organization_id)
        )
    ).scalars().all()
    employee_by_id = {e.id: e for e in employees}

    created_or_updated = 0
    for score in scores:
        emp = employee_by_id.get(score.employee_id)
        role_focus = (emp.role if emp and emp.role else "General")
        weakness = min(
            [
                ("productivity", score.productivity_score),
                ("quality", score.quality_score),
                ("collaboration", score.collaboration_score),
                ("learning", score.learning_score),
            ],
            key=lambda x: x[1],
        )[0]
        plan = (
            f"## Weekly Training Plan\n"
            f"- Focus Role: {role_focus}\n"
            f"- Priority Improvement Area: {weakness}\n"
            f"- Goal: Increase {weakness} score by 10 points this cycle.\n"
            f"- Actions:\n"
            f"  - Pair with top performer in {weakness} domain.\n"
            f"  - Complete 2 measurable tasks tied to {weakness}.\n"
            f"  - Post daily progress report before {settings.MANAGER_REPORT_CUTOFF_HOUR_IST}:00 IST.\n"
        )
        existing = (
            await db.execute(
                select(RoleTrainingPlan).where(
                    RoleTrainingPlan.organization_id == organization_id,
                    RoleTrainingPlan.employee_id == score.employee_id,
                    RoleTrainingPlan.week_start_date == week_start_date,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                RoleTrainingPlan(
                    organization_id=organization_id,
                    employee_id=score.employee_id,
                    week_start_date=week_start_date,
                    role_focus=role_focus,
                    plan_markdown=plan,
                    status="OPEN",
                )
            )
        else:
            existing.role_focus = role_focus
            existing.plan_markdown = plan
            existing.updated_at = datetime.now(timezone.utc)
            db.add(existing)
        created_or_updated += 1
    await db.commit()
    return {"plans_generated": created_or_updated}


async def list_role_training_plans(
    db: AsyncSession,
    *,
    organization_id: int,
    week_start_date: date | None = None,
) -> list[RoleTrainingPlan]:
    query = select(RoleTrainingPlan).where(RoleTrainingPlan.organization_id == organization_id)
    if week_start_date is not None:
        query = query.where(RoleTrainingPlan.week_start_date == week_start_date)
    query = query.order_by(RoleTrainingPlan.week_start_date.desc(), RoleTrainingPlan.employee_id.asc())
    rows = (await db.execute(query)).scalars().all()
    return list(rows)


async def update_role_training_plan_status(
    db: AsyncSession,
    *,
    organization_id: int,
    plan_id: int,
    status: str,
) -> RoleTrainingPlan | None:
    row = (
        await db.execute(
            select(RoleTrainingPlan).where(
                RoleTrainingPlan.organization_id == organization_id,
                RoleTrainingPlan.id == plan_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.status = status
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return cast(RoleTrainingPlan, row)


async def data_quality_snapshot(db: AsyncSession, *, organization_id: int) -> dict[str, object]:
    employees = (
        await db.execute(
            select(Employee).where(Employee.organization_id == organization_id, Employee.is_active.is_(True))
        )
    ).scalars().all()
    emp_ids = [e.id for e in employees]
    identity_rows = await list_identity_maps(db, organization_id=organization_id)
    identity_by_employee = {r.employee_id: r for r in identity_rows}

    missing_identity = 0
    missing_identity_employees: list[int] = []
    for emp_id in emp_ids:
        row = identity_by_employee.get(emp_id)
        if row is None or not any([row.work_email, row.github_login, row.clickup_user_id, row.slack_user_id]):
            missing_identity += 1
            missing_identity_employees.append(emp_id)

    current_week = date.today() - timedelta(days=date.today().weekday())
    stale_metrics = 0
    stale_metric_employees: list[int] = []
    for emp_id in emp_ids:
        has_task = (
            await db.execute(
                select(TaskMetricWeekly.id).where(
                    TaskMetricWeekly.organization_id == organization_id,
                    TaskMetricWeekly.employee_id == emp_id,
                    TaskMetricWeekly.week_start_date == current_week,
                )
            )
        ).scalar_one_or_none()
        has_code = (
            await db.execute(
                select(CodeMetricWeekly.id).where(
                    CodeMetricWeekly.organization_id == organization_id,
                    CodeMetricWeekly.employee_id == emp_id,
                    CodeMetricWeekly.week_start_date == current_week,
                )
            )
        ).scalar_one_or_none()
        has_comms = (
            await db.execute(
                select(CommsMetricWeekly.id).where(
                    CommsMetricWeekly.organization_id == organization_id,
                    CommsMetricWeekly.employee_id == emp_id,
                    CommsMetricWeekly.week_start_date == current_week,
                )
            )
        ).scalar_one_or_none()
        if not (has_task and has_code and has_comms):
            stale_metrics += 1
            stale_metric_employees.append(emp_id)

    # Duplicates conflict check (same work_email linked to many employees)
    dup_q = (
        await db.execute(
            select(EmployeeIdentityMap.work_email, func.count(EmployeeIdentityMap.id))
            .where(
                EmployeeIdentityMap.organization_id == organization_id,
                EmployeeIdentityMap.work_email.is_not(None),
            )
            .group_by(EmployeeIdentityMap.work_email)
            .having(func.count(EmployeeIdentityMap.id) > 1)
        )
    ).all()
    duplicate_conflicts = len(dup_q)

    orphan_approval_count = (
        await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == organization_id,
                Approval.approval_type == "send_message",
                Approval.status == "pending",
                Approval.payload_json.is_(None),
            )
        )
    ).scalar_one()

    return {
        "generated_at": datetime.now(timezone.utc),
        "missing_identity_count": int(missing_identity),
        "stale_metrics_count": int(stale_metrics),
        "duplicate_identity_conflicts": int(duplicate_conflicts),
        "orphan_approval_count": int(orphan_approval_count or 0),
        "details": {
            "missing_identity_employee_ids": missing_identity_employees[:50],
            "stale_metric_employee_ids": stale_metric_employees[:50],
        },
    }


async def manager_sla_snapshot(db: AsyncSession, *, organization_id: int) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=int(settings.APPROVAL_SLA_HOURS))
    pending_breached = (
        await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == organization_id,
                Approval.status == "pending",
                Approval.created_at < cutoff,
            )
        )
    ).scalar_one()

    # Missing manager reports today based on configured prefix
    today = now.date()
    report_prefix = (settings.EMAIL_CONTROL_REPORT_SUBJECT_PREFIX or "[REPORT]").strip().lower()
    reports_today = (
        await db.execute(
            select(func.count(Email.id)).where(
                Email.organization_id == organization_id,
                func.date(Email.created_at) == today,
                Email.subject.ilike(f"{report_prefix}%"),
            )
        )
    ).scalar_one()
    missing_reports = 0 if int(reports_today or 0) > 0 else 1
    status = "ok" if missing_reports == 0 and int(pending_breached or 0) == 0 else "breached"
    return {
        "generated_at": now,
        "missing_reports": int(missing_reports),
        "pending_approvals_breached": int(pending_breached or 0),
        "status": status,
        "details": {"report_prefix": report_prefix, "approval_sla_hours": int(settings.APPROVAL_SLA_HOURS)},
    }
