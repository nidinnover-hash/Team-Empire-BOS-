"""Study abroad (ESA) — application milestones and risk status. BOS is the control plane."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.study_abroad import (
    StudyAbroadApplication,
    StudyAbroadApplicationStep,
    StudyAbroadMilestoneTemplate,
)


async def next_required_steps(
    db: AsyncSession, organization_id: int, application_id: str
) -> dict:
    """Return next required steps for an application from templates and completed steps."""
    app_result = await db.execute(
        select(StudyAbroadApplication)
        .where(
            StudyAbroadApplication.organization_id == organization_id,
            StudyAbroadApplication.external_application_id == application_id,
        )
        .limit(1)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        return {"application_id": application_id, "steps": [], "deadline": None}

    templates_result = await db.execute(
        select(StudyAbroadMilestoneTemplate)
        .where(
            StudyAbroadMilestoneTemplate.organization_id == organization_id,
            StudyAbroadMilestoneTemplate.program_id == app.program_id,
        )
        .order_by(StudyAbroadMilestoneTemplate.order_index)
    )
    templates = list(templates_result.scalars().all())

    steps_result = await db.execute(
        select(StudyAbroadApplicationStep)
        .where(
            StudyAbroadApplicationStep.application_id == app.id,
            StudyAbroadApplicationStep.completed_at.isnot(None),
        )
    )
    completed_keys = {s.step_key for s in steps_result.scalars().all()}

    steps: list[dict] = []
    next_deadline = None
    for t in templates:
        if t.step_key in completed_keys:
            continue
        deadline = None
        if t.days_before_deadline is not None:
            deadline = (datetime.now(UTC) + timedelta(days=t.days_before_deadline)).isoformat()
            if next_deadline is None:
                next_deadline = deadline
        steps.append({"step_key": t.step_key, "step_name": t.step_name, "deadline": deadline})

    return {
        "application_id": application_id,
        "steps": steps,
        "deadline": next_deadline,
    }


async def risk_status(
    db: AsyncSession, organization_id: int, application_id: str
) -> dict:
    """Return risk status from pending deadlines."""
    app_result = await db.execute(
        select(StudyAbroadApplication)
        .where(
            StudyAbroadApplication.organization_id == organization_id,
            StudyAbroadApplication.external_application_id == application_id,
        )
        .limit(1)
    )
    app = app_result.scalar_one_or_none()
    if not app:
        return {
            "application_id": application_id,
            "status": "on_track",
            "message": None,
            "critical_deadlines": [],
        }

    steps_result = await db.execute(
        select(StudyAbroadApplicationStep)
        .where(
            StudyAbroadApplicationStep.application_id == app.id,
            StudyAbroadApplicationStep.deadline.isnot(None),
            StudyAbroadApplicationStep.completed_at.is_(None),
        )
    )
    pending = list(steps_result.scalars().all())
    now = datetime.now(UTC)
    critical: list[str] = []
    for s in pending:
        if s.deadline and s.deadline < now:
            critical.append(s.step_key)

    if critical:
        status = "critical" if len(critical) > 1 else "at_risk"
        message = f"Overdue: {', '.join(critical)}"
    elif pending and any(s.deadline and (s.deadline - now).days <= 3 for s in pending):
        status = "at_risk"
        message = "Deadline within 3 days"
    else:
        status = "on_track"
        message = None

    return {
        "application_id": application_id,
        "status": status,
        "message": message,
        "critical_deadlines": critical,
    }
