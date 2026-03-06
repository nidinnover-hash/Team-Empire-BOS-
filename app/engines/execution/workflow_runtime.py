from __future__ import annotations

from datetime import UTC, datetime

from app.domains.automation import repo as automation_repo
from app.domains.automation import service as automation_domain
from app.domains.automation.models import WorkflowRunStatus, WorkflowStepRunStatus
from app.engines.decision.workflow_plans import build_workflow_execution_plan
from app.engines.execution.workflow_handlers import dispatch_workflow_step_handler
from app.engines.execution.workflow_idempotency import build_workflow_step_idempotency_key
from app.schemas.approval import ApprovalRequestCreate
from app.services import approval as approval_service
from app.services import execution as execution_service


async def run_workflow_plan(
    db,
    *,
    organization_id: int,
    actor_user_id: int,
    run,
    plan: dict[str, object],
) -> object:
    step_runs = await automation_repo.list_workflow_step_runs(db, organization_id=organization_id, workflow_run_id=run.id)
    await automation_domain.mark_run_started(db, run=run, actor_user_id=actor_user_id)
    for step_plan in plan.get("step_plans", []):
        index = int(step_plan["step_index"])
        step_run = next(sr for sr in step_runs if sr.step_index == index)
        step_run.idempotency_key = build_workflow_step_idempotency_key(
            workflow_run_id=run.id,
            step_index=index,
            attempt_count=max(1, int(step_run.attempt_count or 0) + 1),
        )
        decision = str(step_plan.get("decision") or "")
        approval = await approval_service.request_approval(
            db,
            actor_user_id,
            ApprovalRequestCreate(
                organization_id=organization_id,
                approval_type="workflow_step_execute",
                payload_json={
                    "workflow_run_id": run.id,
                    "workflow_definition_id": run.workflow_definition_id,
                    "step_index": index,
                    "step_key": step_run.step_key,
                    "action_type": str(step_plan.get("action_type") or ""),
                    "params": dict(step_plan.get("params") or {}),
                    "decision": decision,
                },
            ),
        )
        step_run.approval_id = approval.id
        if decision == "requires_approval":
            step_run.status = WorkflowStepRunStatus.AWAITING_APPROVAL
            await automation_domain.mark_run_awaiting_approval(
                db,
                run=run,
                actor_user_id=actor_user_id,
                approval_id=approval.id,
                step_index=index,
            )
            await db.commit()
            await db.refresh(run)
            return run
        await approval_service.approve_approval(
            db,
            approval.id,
            actor_user_id,
            organization_id=organization_id,
        )
        await _execute_approved_step(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            run=run,
            step_run=step_run,
            action_type=str(step_plan.get("action_type") or ""),
            params=dict(step_plan.get("params") or {}),
            approval_id=approval.id,
        )
    await automation_domain.mark_run_completed(db, run=run, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(run)
    return run


async def _execute_approved_step(
    db,
    *,
    organization_id: int,
    actor_user_id: int,
    run,
    step_run,
    action_type: str,
    params: dict,
    approval_id: int,
) -> None:
    await automation_domain.mark_step_started(
        db,
        step_run=step_run,
        actor_user_id=actor_user_id,
        workflow_run_id=run.id,
    )
    execution, _created = await execution_service.create_execution(
        db,
        organization_id=organization_id,
        approval_id=approval_id,
        triggered_by=actor_user_id,
        status="running",
        execute_idempotency_key=step_run.idempotency_key,
    )
    try:
        status, output = await dispatch_workflow_step_handler(action_type, params)
        await execution_service.complete_execution(
            db,
            execution.id,
            status=status,
            output_json=output,
            organization_id=organization_id,
        )
        await automation_domain.mark_step_completed(
            db,
            step_run=step_run,
            actor_user_id=actor_user_id,
            workflow_run_id=run.id,
            output_json=output,
            execution_id=execution.id,
            approval_id=approval_id,
            status=WorkflowStepRunStatus.SUCCEEDED if status == "succeeded" else WorkflowStepRunStatus.SKIPPED,
        )
        run.current_step_index = step_run.step_index + 1
        results = dict(run.result_json or {})
        results[f"step_{step_run.step_index}"] = {"status": status, "output": output}
        run.result_json = results
        run.last_heartbeat_at = datetime.now(UTC)
    except Exception as exc:
        error_text = f"{type(exc).__name__}: {str(exc)[:200]}"
        await execution_service.complete_execution(
            db,
            execution.id,
            status="failed",
            error_text=error_text,
            organization_id=organization_id,
        )
        await automation_domain.mark_step_failed(
            db,
            step_run=step_run,
            actor_user_id=actor_user_id,
            workflow_run_id=run.id,
            error_text=error_text,
            execution_id=execution.id,
            approval_id=approval_id,
        )
        await automation_domain.mark_run_failed(
            db,
            run=run,
            actor_user_id=actor_user_id,
            error_summary=error_text,
        )
        try:
            from app.platform.dead_letter.store import capture_failure
            await capture_failure(
                db,
                organization_id=organization_id,
                source_type="workflow",
                source_id=str(run.id),
                source_detail=f"step:{step_run.step_key}:{action_type}",
                payload={
                    "workflow_run_id": run.id,
                    "step_index": step_run.step_index,
                    "step_key": step_run.step_key,
                    "action_type": action_type,
                    "params": params,
                },
                error_message=error_text,
                error_type=type(exc).__name__,
            )
        except Exception:
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "Dead-letter capture failed for workflow run %d", run.id, exc_info=True,
            )
        raise


async def resume_workflow_run_from_approval(
    db,
    *,
    organization_id: int,
    actor_user_id: int,
    approval,
) -> object | None:
    step_run = await automation_repo.get_workflow_step_run_by_approval(
        db,
        organization_id=organization_id,
        approval_id=approval.id,
    )
    if step_run is None:
        return None
    run = await automation_repo.get_workflow_run(
        db,
        organization_id=organization_id,
        workflow_run_id=step_run.workflow_run_id,
    )
    if run is None:
        return None
    payload = approval.payload_json or {}
    await automation_domain.mark_run_started(db, run=run, actor_user_id=actor_user_id)
    await _execute_approved_step(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        run=run,
        step_run=step_run,
        action_type=str(payload.get("action_type") or step_run.action_type),
        params=dict(payload.get("params") or step_run.input_json or {}),
        approval_id=approval.id,
    )
    if run.status != WorkflowRunStatus.FAILED:
        remaining_plans = [
            {
                "step_index": sr.step_index,
                "action_type": sr.action_type,
                "params": dict(sr.input_json or {}),
                "decision": "safe_auto",
            }
            for sr in await automation_repo.list_workflow_step_runs(db, organization_id=organization_id, workflow_run_id=run.id)
            if sr.step_index > step_run.step_index and sr.status in {WorkflowStepRunStatus.PENDING, WorkflowStepRunStatus.QUEUED}
        ]
        if remaining_plans:
            return await run_workflow_plan(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                run=run,
                plan={"step_plans": remaining_plans},
            )
        await automation_domain.mark_run_completed(db, run=run, actor_user_id=actor_user_id)
    await db.commit()
    await db.refresh(run)
    return run


async def reject_workflow_run_from_approval(
    db,
    *,
    organization_id: int,
    actor_user_id: int,
    approval,
) -> object | None:
    step_run = await automation_repo.get_workflow_step_run_by_approval(
        db,
        organization_id=organization_id,
        approval_id=approval.id,
    )
    if step_run is None:
        return None
    run = await automation_repo.get_workflow_run(
        db,
        organization_id=organization_id,
        workflow_run_id=step_run.workflow_run_id,
    )
    if run is None:
        return None
    step_run.status = WorkflowStepRunStatus.CANCELLED
    step_run.error_text = "approval_rejected"
    step_run.finished_at = datetime.now(UTC)
    await automation_domain.mark_run_failed(
        db,
        run=run,
        actor_user_id=actor_user_id,
        error_summary="workflow_step_approval_rejected",
    )
    await db.commit()
    await db.refresh(run)
    return run


async def resume_existing_workflow_run(
    db,
    *,
    organization_id: int,
    actor_user_id: int,
    run,
) -> object:
    step_runs = await automation_repo.list_workflow_step_runs(
        db,
        organization_id=organization_id,
        workflow_run_id=run.id,
    )
    awaiting_step = next(
        (step for step in step_runs if step.status == WorkflowStepRunStatus.AWAITING_APPROVAL),
        None,
    )
    if awaiting_step is not None:
        run.status = WorkflowRunStatus.AWAITING_APPROVAL
        run.current_step_index = awaiting_step.step_index
        run.last_heartbeat_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(run)
        return run

    definition = await automation_domain.get_workflow_definition(
        db,
        organization_id=organization_id,
        workflow_definition_id=run.workflow_definition_id,
    )
    if definition is None:
        await automation_domain.mark_run_failed(
            db,
            run=run,
            actor_user_id=actor_user_id,
            error_summary="workflow_definition_missing",
        )
        await db.commit()
        await db.refresh(run)
        return run

    step_plans = list((run.plan_snapshot_json or {}).get("step_plans") or [])
    if not step_plans:
        plan = await build_workflow_execution_plan(
            db,
            organization_id=organization_id,
            workspace_id=run.workspace_id,
            actor_user_id=actor_user_id,
            run=run,
            definition=definition,
        )
        run.plan_snapshot_json = plan
        step_plans = list(plan.get("step_plans") or [])

    start_index = min(
        (
            step.step_index
            for step in step_runs
            if step.status
            not in {
                WorkflowStepRunStatus.SUCCEEDED,
                WorkflowStepRunStatus.SKIPPED,
                WorkflowStepRunStatus.CANCELLED,
            }
        ),
        default=int(run.current_step_index or 0),
    )

    for step_run in step_runs:
        if step_run.step_index < start_index:
            continue
        if step_run.status in {
            WorkflowStepRunStatus.FAILED,
            WorkflowStepRunStatus.RUNNING,
            WorkflowStepRunStatus.QUEUED,
        }:
            step_run.status = WorkflowStepRunStatus.PENDING
            step_run.error_text = None
            step_run.started_at = None
            step_run.finished_at = None
            step_run.execution_id = None
            step_run.approval_id = None

    remaining_plans = [
        step_plan
        for step_plan in step_plans
        if int(step_plan.get("step_index") or 0) >= start_index
    ]
    if not remaining_plans:
        await automation_domain.mark_run_completed(db, run=run, actor_user_id=actor_user_id)
        await db.commit()
        await db.refresh(run)
        return run

    run.status = WorkflowRunStatus.PENDING
    run.error_summary = None
    run.finished_at = None
    run.next_retry_at = None
    run.current_step_index = start_index
    run.last_heartbeat_at = datetime.now(UTC)
    return await run_workflow_plan(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        run=run,
        plan={"step_plans": remaining_plans},
    )
