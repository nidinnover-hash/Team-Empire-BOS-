"""Innovation experiment tracker — structured hypothesis testing with data-driven outcomes."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_experiment import BusinessExperiment

logger = logging.getLogger(__name__)


async def create_experiment(
    db: AsyncSession,
    org_id: int,
    title: str,
    hypothesis: str,
    success_metric: str,
    *,
    area: str = "general",
    baseline_value: float | None = None,
    target_value: float | None = None,
    created_by: int | None = None,
) -> BusinessExperiment:
    """Create a new business experiment."""
    exp = BusinessExperiment(
        organization_id=org_id,
        created_by=created_by,
        title=title,
        hypothesis=hypothesis,
        success_metric=success_metric,
        area=area,
        baseline_value=baseline_value,
        target_value=target_value,
        status="proposed",
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return exp


async def start_experiment(
    db: AsyncSession,
    org_id: int,
    experiment_id: int,
) -> BusinessExperiment | None:
    """Activate a proposed experiment."""
    result = await db.execute(
        select(BusinessExperiment).where(
            BusinessExperiment.id == experiment_id,
            BusinessExperiment.organization_id == org_id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        return None
    exp.status = "active"
    exp.start_date = datetime.now(UTC)
    await db.commit()
    await db.refresh(exp)
    return exp


async def complete_experiment(
    db: AsyncSession,
    org_id: int,
    experiment_id: int,
    actual_value: float,
    outcome: str,
    outcome_notes: str | None = None,
) -> BusinessExperiment | None:
    """Record experiment outcome and close it."""
    result = await db.execute(
        select(BusinessExperiment).where(
            BusinessExperiment.id == experiment_id,
            BusinessExperiment.organization_id == org_id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        return None
    exp.status = "completed"
    exp.actual_value = actual_value
    exp.outcome = outcome
    exp.outcome_notes = outcome_notes
    exp.end_date = datetime.now(UTC)
    await db.commit()
    await db.refresh(exp)
    return exp


async def list_experiments(
    db: AsyncSession,
    org_id: int,
    status: str | None = None,
    area: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[BusinessExperiment]:
    """List experiments with optional filters."""
    query = select(BusinessExperiment).where(
        BusinessExperiment.organization_id == org_id,
    )
    if status:
        query = query.where(BusinessExperiment.status == status)
    if area:
        query = query.where(BusinessExperiment.area == area)
    query = query.order_by(BusinessExperiment.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_experiment(
    db: AsyncSession,
    org_id: int,
    experiment_id: int,
) -> BusinessExperiment | None:
    """Get a single experiment."""
    result = await db.execute(
        select(BusinessExperiment).where(
            BusinessExperiment.id == experiment_id,
            BusinessExperiment.organization_id == org_id,
        )
    )
    return result.scalar_one_or_none()


async def get_innovation_velocity(
    db: AsyncSession,
    org_id: int,
    days: int = 90,
) -> dict:
    """Measure innovation velocity — experiments run, success rate, areas covered."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(BusinessExperiment).where(
            BusinessExperiment.organization_id == org_id,
            BusinessExperiment.created_at >= cutoff,
        )
    )
    experiments = list(result.scalars().all())

    total = len(experiments)
    completed = [e for e in experiments if e.status == "completed"]
    active = sum(1 for e in experiments if e.status == "active")
    proposed = sum(1 for e in experiments if e.status == "proposed")
    successes = sum(1 for e in completed if e.outcome == "success")
    failures = sum(1 for e in completed if e.outcome == "failure")

    areas: dict[str, int] = {}
    for e in experiments:
        areas[e.area] = areas.get(e.area, 0) + 1

    months = max(1, days / 30)
    velocity = round(total / months, 1)
    success_rate = round(successes / len(completed) if completed else 0.0, 3)

    return {
        "window_days": days,
        "total_experiments": total,
        "active": active,
        "proposed": proposed,
        "completed": len(completed),
        "successes": successes,
        "failures": failures,
        "success_rate": success_rate,
        "experiments_per_month": velocity,
        "areas": areas,
    }
