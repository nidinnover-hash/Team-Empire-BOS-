from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.signal import Signal
from app.models.workflow_run import WorkflowRun, WorkflowStepRun


async def get_workflow_observability_summary(
    db: AsyncSession,
    *,
    organization_id: int,
    days: int = 7,
) -> dict[str, object]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    runs = (
        await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.created_at >= cutoff,
            )
        )
    ).scalars().all()
    total_runs = len(runs)
    awaiting_approval = sum(1 for run in runs if str(run.status) == "awaiting_approval")
    completed = sum(1 for run in runs if str(run.status) == "completed")
    failed = sum(1 for run in runs if str(run.status) == "failed")
    retry_wait = sum(1 for run in runs if str(run.status) == "retry_wait")
    paused = sum(1 for run in runs if str(run.status) == "paused")
    stuck_runs = sum(
        1
        for run in runs
        if str(run.status) in {"running", "awaiting_approval", "retry_wait"}
        and run.last_heartbeat_at is not None
        and run.last_heartbeat_at < datetime.now(UTC) - timedelta(hours=1)
    )
    durations_ms = [
        int((run.finished_at - run.started_at).total_seconds() * 1000)
        for run in runs
        if run.started_at is not None and run.finished_at is not None
    ]
    avg_latency_ms = int(sum(durations_ms) / len(durations_ms)) if durations_ms else None
    ai_plans = await db.scalar(
        select(func.count(Signal.id)).where(
            Signal.organization_id == organization_id,
            Signal.topic == "workflow.plan.generated",
            Signal.occurred_at >= cutoff,
        )
    )
    return {
        "days": days,
        "total_runs": total_runs,
        "awaiting_approval": awaiting_approval,
        "completed": completed,
        "failed": failed,
        "retry_wait": retry_wait,
        "paused": paused,
        "stuck_runs": stuck_runs,
        "success_rate": round((completed / total_runs) * 100, 2) if total_runs else 0.0,
        "avg_latency_ms": avg_latency_ms,
        "ai_plans": int(ai_plans or 0),
    }


async def list_workflow_observability_runs(
    db: AsyncSession,
    *,
    organization_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[WorkflowRun]:
    query = (
        select(WorkflowRun)
        .where(WorkflowRun.organization_id == organization_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(WorkflowRun.status == status)
    return list((await db.execute(query)).scalars().all())


async def get_workflow_observability_run_detail(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
) -> dict[str, object] | None:
    run = (
        await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.id == workflow_run_id,
            )
        )
    ).scalar_one_or_none()
    if run is None:
        return None
    steps = (
        await db.execute(
            select(WorkflowStepRun)
            .where(
                WorkflowStepRun.organization_id == organization_id,
                WorkflowStepRun.workflow_run_id == workflow_run_id,
            )
            .order_by(WorkflowStepRun.step_index.asc())
        )
    ).scalars().all()
    return {"run": run, "step_runs": list(steps)}


async def list_workflow_failures(
    db: AsyncSession,
    *,
    organization_id: int,
    limit: int = 50,
) -> list[WorkflowRun]:
    return list(
        (
            await db.execute(
                select(WorkflowRun)
                .where(
                    WorkflowRun.organization_id == organization_id,
                    WorkflowRun.status == "failed",
                )
                .order_by(WorkflowRun.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )


async def list_workflow_approval_backlog(
    db: AsyncSession,
    *,
    organization_id: int,
    limit: int = 50,
) -> list[Approval]:
    return list(
        (
            await db.execute(
                select(Approval)
                .where(
                    Approval.organization_id == organization_id,
                    Approval.approval_type == "workflow_step_execute",
                )
                .order_by(Approval.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )


async def list_ai_workflow_plans(
    db: AsyncSession,
    *,
    organization_id: int,
    limit: int = 50,
) -> list[Signal]:
    return list(
        (
            await db.execute(
                select(Signal)
                .where(
                    Signal.organization_id == organization_id,
                    Signal.topic == "workflow.plan.generated",
                )
                .order_by(Signal.occurred_at.desc())
                .limit(limit)
            )
        ).scalars().all()
    )
