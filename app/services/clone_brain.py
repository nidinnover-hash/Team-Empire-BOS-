from __future__ import annotations

from datetime import date
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clone_performance import ClonePerformanceWeekly
from app.models.clone_control import EmployeeCloneProfile
from app.models.employee import Employee
from app.models.ops_metrics import CodeMetricWeekly, CommsMetricWeekly, TaskMetricWeekly
from app.services import clone_control


class CloneDispatchItem(TypedDict):
    employee_id: int
    employee_name: str
    role: str | None
    overall_score: float
    readiness_level: str
    fit_reason: str


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, value))


def _readiness(score: float) -> str:
    if score >= 85:
        return "elite"
    if score >= 70:
        return "strong"
    if score >= 55:
        return "developing"
    return "needs_support"


async def train_weekly_clone_scores(
    db: AsyncSession,
    *,
    organization_id: int,
    week_start_date: date,
) -> dict[str, object]:
    employees = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == organization_id,
                Employee.is_active.is_(True),
            )
        )
    ).scalars().all()

    upserted = 0
    for emp in employees:
        tm = (
            await db.execute(
                select(TaskMetricWeekly).where(
                    TaskMetricWeekly.organization_id == organization_id,
                    TaskMetricWeekly.employee_id == emp.id,
                    TaskMetricWeekly.week_start_date == week_start_date,
                )
            )
        ).scalar_one_or_none()
        cm = (
            await db.execute(
                select(CodeMetricWeekly).where(
                    CodeMetricWeekly.organization_id == organization_id,
                    CodeMetricWeekly.employee_id == emp.id,
                    CodeMetricWeekly.week_start_date == week_start_date,
                )
            )
        ).scalar_one_or_none()
        xm = (
            await db.execute(
                select(CommsMetricWeekly).where(
                    CommsMetricWeekly.organization_id == organization_id,
                    CommsMetricWeekly.employee_id == emp.id,
                    CommsMetricWeekly.week_start_date == week_start_date,
                )
            )
        ).scalar_one_or_none()

        productivity = _bounded(
            (float(tm.tasks_completed) * 4.0 if tm else 0.0)
            + (float(cm.prs_merged) * 3.0 if cm else 0.0)
            + (float(xm.emails_replied) * 0.8 if xm else 0.0)
        )
        quality = _bounded(
            (float(tm.on_time_rate) * 50.0 if tm else 0.0)
            + (float(cm.reviews_done) * 2.0 if cm else 0.0)
            - (float(tm.reopen_count) * 3.5 if tm else 0.0)
        )
        collaboration = _bounded(
            (float(cm.reviews_done) * 3.0 if cm else 0.0)
            + (30.0 if xm and xm.median_reply_time_minutes <= 120 else 10.0 if xm else 0.0)
            - (float(xm.escalation_count) * 4.0 if xm else 0.0)
        )
        learning = _bounded(
            (float(cm.issue_links) * 2.0 if cm else 0.0)
            + (float(cm.files_touched_count) * 0.2 if cm else 0.0)
            + (10.0 if tm and (tm.notes or "").strip() else 0.0)
        )
        overall = round(
            (productivity * 0.35)
            + (quality * 0.30)
            + (collaboration * 0.20)
            + (learning * 0.15),
            2,
        )
        feedback_adj = await clone_control.feedback_adjustment_for_employee(
            db,
            organization_id=organization_id,
            employee_id=emp.id,
            lookback_days=30,
        )
        overall = round(max(0.0, min(100.0, overall + feedback_adj)), 2)
        readiness = _readiness(overall)

        existing = (
            await db.execute(
                select(ClonePerformanceWeekly).where(
                    ClonePerformanceWeekly.organization_id == organization_id,
                    ClonePerformanceWeekly.employee_id == emp.id,
                    ClonePerformanceWeekly.week_start_date == week_start_date,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ClonePerformanceWeekly(
                    organization_id=organization_id,
                    employee_id=emp.id,
                    week_start_date=week_start_date,
                    productivity_score=productivity,
                    quality_score=quality,
                    collaboration_score=collaboration,
                    learning_score=learning,
                    overall_score=overall,
                    readiness_level=readiness,
                )
            )
        else:
            existing.productivity_score = productivity
            existing.quality_score = quality
            existing.collaboration_score = collaboration
            existing.learning_score = learning
            existing.overall_score = overall
            existing.readiness_level = readiness
            db.add(existing)
        upserted += 1

    await db.commit()
    return {"week_start_date": week_start_date.isoformat(), "employees_scored": upserted}


async def list_clone_scores(
    db: AsyncSession,
    *,
    organization_id: int,
    week_start_date: date | None,
) -> list[ClonePerformanceWeekly]:
    query = select(ClonePerformanceWeekly).where(ClonePerformanceWeekly.organization_id == organization_id)
    if week_start_date is not None:
        query = query.where(ClonePerformanceWeekly.week_start_date == week_start_date)
    query = query.order_by(ClonePerformanceWeekly.overall_score.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def clone_org_summary(
    db: AsyncSession,
    *,
    organization_id: int,
    week_start_date: date | None,
) -> dict[str, object]:
    scores = await list_clone_scores(db, organization_id=organization_id, week_start_date=week_start_date)
    if not scores:
        return {"count": 0, "avg_score": 0.0, "elite": 0, "strong": 0, "developing": 0, "needs_support": 0}
    avg = round(sum(s.overall_score for s in scores) / len(scores), 2)
    buckets = {"elite": 0, "strong": 0, "developing": 0, "needs_support": 0}
    for s in scores:
        buckets[s.readiness_level] = buckets.get(s.readiness_level, 0) + 1
    return {"count": len(scores), "avg_score": avg, **buckets}


async def build_dispatch_plan(
    db: AsyncSession,
    *,
    organization_id: int,
    challenge: str,
    week_start_date: date | None,
    top_n: int = 3,
) -> list[CloneDispatchItem]:
    scores = await list_clone_scores(db, organization_id=organization_id, week_start_date=week_start_date)
    if not scores:
        return []
    employees = (
        await db.execute(select(Employee).where(Employee.organization_id == organization_id))
    ).scalars().all()
    by_id = {e.id: e for e in employees}
    picks: list[CloneDispatchItem] = []
    challenge_text = challenge.lower()
    for row in scores[: max(1, min(top_n, 10))]:
        emp = by_id.get(row.employee_id)
        if not emp:
            continue
        reason = "High overall clone readiness for complex execution."
        profile = (
            await db.execute(
                select(EmployeeCloneProfile).where(
                    EmployeeCloneProfile.organization_id == organization_id,
                    EmployeeCloneProfile.employee_id == emp.id,
                )
            )
        ).scalar_one_or_none()
        preferred = []
        if profile is not None:
            import json

            preferred = [str(x).lower() for x in json.loads(profile.preferred_task_types_json or "[]")]
        role_text = (emp.role or "").lower()
        if "tech" in challenge_text and ("developer" in role_text or "engineer" in role_text):
            reason = "Strong technical fit based on role and performance score."
        elif "sales" in challenge_text and ("sales" in role_text or "counsellor" in role_text):
            reason = "Strong client-facing fit based on role and performance score."
        elif any(token in challenge_text for token in preferred):
            reason = "Strong fit from preferred task types and historical outcomes."
        picks.append(
            {
                "employee_id": emp.id,
                "employee_name": emp.name,
                "role": emp.role,
                "overall_score": row.overall_score,
                "readiness_level": row.readiness_level,
                "fit_reason": reason,
            }
        )
    return picks
