from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.domains.automation import service as automation_domain
from app.domains.automation.models import WorkflowRunStatus
from app.engines.execution.workflow_retry_policy import (
    should_mark_run_stuck,
    should_resume_retry_wait_run,
)
from app.engines.execution.workflow_runtime import resume_existing_workflow_run
from app.models.workflow_run import WorkflowRun


async def recover_workflow_runs_for_org(
    db,
    *,
    organization_id: int,
    actor_user_id: int | None = None,
    limit: int = 100,
) -> dict[str, int]:
    current = datetime.now(UTC)
    result = await db.execute(
        select(WorkflowRun)
        .where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.status.in_(
                [
                    WorkflowRunStatus.RUNNING,
                    WorkflowRunStatus.RETRY_WAIT,
                ]
            ),
        )
        .order_by(WorkflowRun.updated_at.asc())
        .limit(limit)
    )
    runs = list(result.scalars().all())

    recovered = 0
    failed = 0
    inspected = len(runs)
    recovery_actor = actor_user_id if actor_user_id is not None else int((runs[0].requested_by if runs else 0) or 0)

    for run in runs:
        if should_mark_run_stuck(run=run, now=current):
            await automation_domain.mark_run_failed(
                db,
                run=run,
                actor_user_id=actor_user_id,
                error_summary="workflow_run_stuck_timeout",
            )
            failed += 1
            continue

        if should_resume_retry_wait_run(run=run, now=current):
            await resume_existing_workflow_run(
                db,
                organization_id=organization_id,
                actor_user_id=int(run.requested_by or recovery_actor or 0),
                run=run,
            )
            recovered += 1

    if inspected:
        await db.commit()
    return {"inspected": inspected, "recovered": recovered, "failed": failed}
