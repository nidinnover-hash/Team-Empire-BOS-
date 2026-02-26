"""Scheduler job runs, replay, and execute-plan endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.ceo_control import SchedulerJobRun
from app.schemas.control import (
    ExecutePlanRead,
    ExecutePlanRequest,
    SchedulerJobRunListRead,
    SchedulerReplayRead,
    SchedulerReplayRequest,
)
from app.services import (
    clone_brain,
    clone_control,
    compliance_engine,
    email_control,
    sync_scheduler,
)

router = APIRouter()


@router.get("/jobs/runs", response_model=SchedulerJobRunListRead)
async def scheduler_job_runs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SchedulerJobRunListRead:
    org_id = int(actor["org_id"])
    safe_limit = max(1, min(limit, 200))
    rows = (
        await db.execute(
            select(SchedulerJobRun)
            .where(SchedulerJobRun.organization_id == org_id)
            .order_by(SchedulerJobRun.started_at.desc())
            .limit(safe_limit)
        )
    ).scalars().all()
    runs_by_job: dict[str, list[SchedulerJobRun]] = {}
    for row in rows:
        runs_by_job.setdefault(row.job_name, []).append(row)
    items: list[dict[str, Any]] = []
    for row in rows:
        job_runs = sorted(runs_by_job.get(row.job_name, []), key=lambda r: r.started_at, reverse=True)
        failure_streak = 0
        for run in job_runs:
            if run.status == "error":
                failure_streak += 1
            else:
                break
        retry_backoff_seconds: int | None = None
        suggested_next_retry_at: datetime | None = None
        if row.status == "error":
            backoff_seconds = min(3600, 60 * (2 ** max(0, failure_streak - 1)))
            retry_backoff_seconds = backoff_seconds
            suggested_next_retry_at = row.started_at + timedelta(seconds=backoff_seconds)
        dead_letter_candidate = bool(row.status == "error" and failure_streak >= 3)
        items.append(
            {
                "id": row.id,
                "job_name": row.job_name,
                "status": row.status,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "duration_ms": row.duration_ms,
                "details": json.loads(row.details_json or "{}"),
                "error": row.error,
                "failure_streak": failure_streak,
                "retry_backoff_seconds": retry_backoff_seconds,
                "suggested_next_retry_at": suggested_next_retry_at,
                "dead_letter_candidate": dead_letter_candidate,
            }
        )
    return SchedulerJobRunListRead(count=len(items), items=items)


@router.post("/jobs/replay", response_model=SchedulerReplayRead)
async def scheduler_job_replay(
    payload: SchedulerReplayRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SchedulerReplayRead:
    org_id = int(actor["org_id"])
    result = await sync_scheduler.replay_job_for_org(db, org_id, payload.job_name)
    return SchedulerReplayRead(
        ok=bool(result.get("ok")),
        job_name=str(result.get("job_name") or payload.job_name),
        result=result.get("result") if isinstance(result.get("result"), dict) else None,
        error=str(result.get("error")) if result.get("error") else None,
    )


@router.post("/execute-plan", response_model=ExecutePlanRead)
async def execute_plan(
    payload: ExecutePlanRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ExecutePlanRead:
    org_id = int(actor["org_id"])
    sync_result = await sync_scheduler.replay_job_for_org(db, org_id, "full_sync")
    email_result = await email_control.process_inbox_controls(
        db,
        org_id=org_id,
        actor_user_id=int(actor["id"]),
        limit=100,
    )
    compliance = await compliance_engine.run_compliance(db, org_id)
    challenge = (payload.challenge or "Complex execution dispatch").strip()
    dispatch = await clone_brain.build_dispatch_plan(
        db,
        organization_id=org_id,
        challenge=challenge,
        week_start_date=(payload.week_start_date.date() if payload.week_start_date else None),
        top_n=3,
    )
    quality = await clone_control.data_quality_snapshot(db, organization_id=org_id)
    return ExecutePlanRead(
        ok=True,
        sync=sync_result,
        email_control=email_result,
        compliance={"score": compliance.get("compliance_score"), "violations": len(compliance.get("violations", []))},
        dispatch_plan=dispatch,
        data_quality={
            "missing_identity_count": quality["missing_identity_count"],
            "stale_metrics_count": quality["stale_metrics_count"],
            "duplicate_identity_conflicts": quality["duplicate_identity_conflicts"],
            "orphan_approval_count": quality["orphan_approval_count"],
        },
    )
