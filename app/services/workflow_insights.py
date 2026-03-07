"""Workflow Execution Insights — analytics for workflow runs and step performance."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, cast, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_run import WorkflowRun, WorkflowStepRun


async def get_execution_summary(
    db: AsyncSession,
    organization_id: int,
    *,
    days: int = 30,
) -> dict:
    """High-level execution stats: total runs, success/failure/pending counts, avg duration."""
    since = datetime.now(UTC) - timedelta(days=days)

    q = (
        select(
            func.count(WorkflowRun.id).label("total"),
            func.sum(case((WorkflowRun.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((WorkflowRun.status == "failed", 1), else_=0)).label("failed"),
            func.sum(case((WorkflowRun.status == "running", 1), else_=0)).label("running"),
            func.sum(case((WorkflowRun.status == "pending", 1), else_=0)).label("pending"),
            func.sum(case((WorkflowRun.status == "cancelled", 1), else_=0)).label("cancelled"),
        )
        .where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.created_at >= since,
        )
    )
    row = (await db.execute(q)).one()

    total = row.total or 0
    completed = row.completed or 0
    failed = row.failed or 0

    return {
        "total_runs": total,
        "completed": completed,
        "failed": failed,
        "running": row.running or 0,
        "pending": row.pending or 0,
        "cancelled": row.cancelled or 0,
        "success_rate": round(completed / total, 4) if total > 0 else 0.0,
        "failure_rate": round(failed / total, 4) if total > 0 else 0.0,
        "period_days": days,
    }


async def get_step_performance(
    db: AsyncSession,
    organization_id: int,
    *,
    days: int = 30,
    limit: int = 20,
) -> list[dict]:
    """Per-action-type step performance: avg/p50/p95 latency, failure rate."""
    since = datetime.now(UTC) - timedelta(days=days)

    q = (
        select(
            WorkflowStepRun.action_type,
            func.count(WorkflowStepRun.id).label("total"),
            func.sum(case((WorkflowStepRun.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((WorkflowStepRun.status == "failed", 1), else_=0)).label("failed"),
            func.avg(WorkflowStepRun.latency_ms).label("avg_latency_ms"),
            func.min(WorkflowStepRun.latency_ms).label("min_latency_ms"),
            func.max(WorkflowStepRun.latency_ms).label("max_latency_ms"),
        )
        .where(
            WorkflowStepRun.organization_id == organization_id,
            WorkflowStepRun.created_at >= since,
        )
        .group_by(WorkflowStepRun.action_type)
        .order_by(func.count(WorkflowStepRun.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()

    results = []
    for r in rows:
        total = r.total or 0
        failed = r.failed or 0
        results.append({
            "action_type": r.action_type,
            "total_executions": total,
            "completed": r.completed or 0,
            "failed": failed,
            "failure_rate": round(failed / total, 4) if total > 0 else 0.0,
            "avg_latency_ms": round(r.avg_latency_ms) if r.avg_latency_ms else None,
            "min_latency_ms": r.min_latency_ms,
            "max_latency_ms": r.max_latency_ms,
        })
    return results


async def get_workflow_rankings(
    db: AsyncSession,
    organization_id: int,
    *,
    days: int = 30,
    limit: int = 10,
) -> list[dict]:
    """Top workflows by run count, with success rates."""
    since = datetime.now(UTC) - timedelta(days=days)

    q = (
        select(
            WorkflowRun.workflow_definition_id,
            WorkflowDefinition.name.label("workflow_name"),
            func.count(WorkflowRun.id).label("total"),
            func.sum(case((WorkflowRun.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((WorkflowRun.status == "failed", 1), else_=0)).label("failed"),
        )
        .join(WorkflowDefinition, WorkflowRun.workflow_definition_id == WorkflowDefinition.id)
        .where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.created_at >= since,
        )
        .group_by(WorkflowRun.workflow_definition_id, WorkflowDefinition.name)
        .order_by(func.count(WorkflowRun.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()

    results = []
    for r in rows:
        total = r.total or 0
        completed = r.completed or 0
        results.append({
            "workflow_definition_id": r.workflow_definition_id,
            "workflow_name": r.workflow_name,
            "total_runs": total,
            "completed": completed,
            "failed": r.failed or 0,
            "success_rate": round(completed / total, 4) if total > 0 else 0.0,
        })
    return results


async def get_failure_patterns(
    db: AsyncSession,
    organization_id: int,
    *,
    days: int = 30,
    limit: int = 10,
) -> list[dict]:
    """Most common failure error summaries from recent workflow runs."""
    since = datetime.now(UTC) - timedelta(days=days)

    q = (
        select(
            WorkflowRun.error_summary,
            WorkflowRun.workflow_definition_id,
            WorkflowDefinition.name.label("workflow_name"),
            func.count(WorkflowRun.id).label("count"),
            func.max(WorkflowRun.created_at).label("last_seen"),
        )
        .join(WorkflowDefinition, WorkflowRun.workflow_definition_id == WorkflowDefinition.id)
        .where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.status == "failed",
            WorkflowRun.error_summary.isnot(None),
            WorkflowRun.created_at >= since,
        )
        .group_by(WorkflowRun.error_summary, WorkflowRun.workflow_definition_id, WorkflowDefinition.name)
        .order_by(func.count(WorkflowRun.id).desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()

    return [
        {
            "error_summary": r.error_summary,
            "workflow_definition_id": r.workflow_definition_id,
            "workflow_name": r.workflow_name,
            "count": r.count,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
        }
        for r in rows
    ]


async def get_daily_run_counts(
    db: AsyncSession,
    organization_id: int,
    *,
    days: int = 30,
) -> list[dict]:
    """Daily run counts grouped by status for charting."""
    since = datetime.now(UTC) - timedelta(days=days)

    # Use date truncation — cast created_at to date
    date_col = cast(WorkflowRun.created_at, type_=_date_type())

    q = (
        select(
            date_col.label("date"),
            func.count(WorkflowRun.id).label("total"),
            func.sum(case((WorkflowRun.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((WorkflowRun.status == "failed", 1), else_=0)).label("failed"),
        )
        .where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.created_at >= since,
        )
        .group_by(date_col)
        .order_by(date_col)
    )
    rows = (await db.execute(q)).all()

    return [
        {
            "date": str(r.date),
            "total": r.total or 0,
            "completed": r.completed or 0,
            "failed": r.failed or 0,
        }
        for r in rows
    ]


def _date_type():
    """Return SA Date type for cast operations."""
    from sqlalchemy import Date
    return Date()


async def get_full_insights(
    db: AsyncSession,
    organization_id: int,
    *,
    days: int = 30,
) -> dict:
    """Aggregate all insight data into a single response."""
    summary = await get_execution_summary(db, organization_id, days=days)
    step_perf = await get_step_performance(db, organization_id, days=days)
    rankings = await get_workflow_rankings(db, organization_id, days=days)
    failures = await get_failure_patterns(db, organization_id, days=days)
    daily = await get_daily_run_counts(db, organization_id, days=days)

    return {
        "summary": summary,
        "step_performance": step_perf,
        "workflow_rankings": rankings,
        "failure_patterns": failures,
        "daily_counts": daily,
    }
