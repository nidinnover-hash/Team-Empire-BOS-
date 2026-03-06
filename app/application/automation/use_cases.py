from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.automation import service as automation_domain
from app.domains.automation.models import WorkflowDefinitionStatus, WorkflowRunStatus
from app.engines.decision.workflow_plans import build_workflow_execution_plan
from app.engines.execution.workflow_retry_policy import compute_next_retry_at
from app.engines.execution.workflow_runtime import resume_existing_workflow_run, run_workflow_plan
from app.logs.audit import record_action
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_run import WorkflowRun


async def create_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workspace_id: int | None,
    actor_user_id: int,
    data,
) -> WorkflowDefinition:
    row = await automation_domain.create_workflow_definition(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        name=data.name,
        description=data.description,
        trigger_mode=data.trigger_mode,
        trigger_spec_json=data.trigger_spec_json,
        steps_json=[step.model_dump() for step in data.steps],
        defaults_json=data.defaults_json,
        risk_level=data.risk_level,
    )
    await record_action(
        db,
        event_type="workflow_definition_created",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type="workflow_definition",
        entity_id=row.id,
        payload_json={"workspace_id": workspace_id, "status": row.status},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def list_workflow_definitions(
    db: AsyncSession,
    *,
    organization_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[WorkflowDefinition]:
    return await automation_domain.list_workflow_definitions(db, organization_id=organization_id, status=status, limit=limit)


async def update_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_definition_id: int,
    actor_user_id: int,
    data,
) -> WorkflowDefinition | None:
    steps = None
    if data.steps is not None:
        steps = [step.model_dump() for step in data.steps]
    row = await automation_domain.update_workflow_definition(
        db,
        organization_id=organization_id,
        workflow_definition_id=workflow_definition_id,
        actor_user_id=actor_user_id,
        name=data.name,
        description=data.description,
        trigger_mode=data.trigger_mode,
        trigger_spec_json=data.trigger_spec_json,
        steps_json=steps,
        defaults_json=data.defaults_json,
        risk_level=data.risk_level,
    )
    if row is None:
        return None
    await record_action(
        db,
        event_type="workflow_definition_updated",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type="workflow_definition",
        entity_id=row.id,
        payload_json={"status": row.status},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def publish_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_definition_id: int,
    actor_user_id: int,
) -> WorkflowDefinition | None:
    row = await automation_domain.publish_workflow_definition(
        db,
        organization_id=organization_id,
        workflow_definition_id=workflow_definition_id,
        actor_user_id=actor_user_id,
    )
    if row is None:
        return None
    await record_action(
        db,
        event_type="workflow_definition_published",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type="workflow_definition",
        entity_id=row.id,
        payload_json={"version": row.version, "status": row.status},
    )
    await db.commit()
    await db.refresh(row)
    return row


async def preview_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    workspace_id: int | None,
    actor_user_id: int,
    workflow_definition_id: int,
    input_json: dict | None = None,
) -> dict[str, object] | None:
    definition = await automation_domain.get_workflow_definition(
        db,
        organization_id=organization_id,
        workflow_definition_id=workflow_definition_id,
    )
    if definition is None:
        return None
    synthetic_run = type("PreviewRun", (), {"id": 0})()
    plan = await build_workflow_execution_plan(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        run=synthetic_run,
        definition=definition,
    )
    return {
        "workflow_definition_id": definition.id,
        "workflow_status": definition.status,
        "input_json": input_json or {},
        "requires_publish": definition.status != WorkflowDefinitionStatus.PUBLISHED,
        "step_plans": plan["step_plans"],
    }


async def run_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workspace_id: int | None,
    actor_user_id: int,
    workflow_definition_id: int,
    trigger_source: str,
    input_json: dict | None = None,
    trigger_signal_id: str | None = None,
    idempotency_key: str | None = None,
) -> WorkflowRun | None:
    definition = await automation_domain.get_workflow_definition(
        db,
        organization_id=organization_id,
        workflow_definition_id=workflow_definition_id,
    )
    if definition is None or definition.status != WorkflowDefinitionStatus.PUBLISHED:
        return None
    run, _steps = await automation_domain.create_workflow_run(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        definition=definition,
        trigger_source=trigger_source,
        trigger_signal_id=trigger_signal_id,
        idempotency_key=idempotency_key or f"workflow-definition:{workflow_definition_id}:actor:{actor_user_id}:trigger:{trigger_source}",
        input_json=input_json or {},
        context_json={},
        plan_snapshot_json={},
    )
    plan = await build_workflow_execution_plan(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        run=run,
        definition=definition,
    )
    run.plan_snapshot_json = plan
    await record_action(
        db,
        event_type="workflow_run_requested",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type="workflow_run",
        entity_id=run.id,
        payload_json={
            "workflow_definition_id": definition.id,
            "trigger_source": trigger_source,
            "step_count": len(plan.get("step_plans", [])),
        },
    )
    result = await run_workflow_plan(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        run=run,
        plan=plan,
    )
    await db.commit()
    await db.refresh(result)
    return result


async def list_workflow_runs(
    db: AsyncSession,
    *,
    organization_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[WorkflowRun]:
    return await automation_domain.list_workflow_runs(db, organization_id=organization_id, status=status, limit=limit)


async def get_workflow_run_detail(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
) -> dict[str, object] | None:
    run = await automation_domain.get_workflow_run(db, organization_id=organization_id, workflow_run_id=workflow_run_id)
    if run is None:
        return None
    steps = await automation_domain.get_workflow_step_runs(db, organization_id=organization_id, workflow_run_id=workflow_run_id)
    return {"run": run, "step_runs": steps}


async def pause_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
    actor_user_id: int,
) -> WorkflowRun | None:
    run = await automation_domain.get_workflow_run(db, organization_id=organization_id, workflow_run_id=workflow_run_id)
    if run is None or run.status not in {WorkflowRunStatus.RUNNING, WorkflowRunStatus.AWAITING_APPROVAL}:
        return None
    run.status = WorkflowRunStatus.PAUSED
    await record_action(
        db,
        event_type="workflow_run_paused",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type="workflow_run",
        entity_id=run.id,
        payload_json={"status": run.status},
    )
    await db.commit()
    await db.refresh(run)
    return run


async def resume_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    actor_user_id: int,
    workflow_run_id: int,
) -> WorkflowRun | None:
    run = await automation_domain.get_workflow_run(db, organization_id=organization_id, workflow_run_id=workflow_run_id)
    if run is None or run.status not in {WorkflowRunStatus.PAUSED, WorkflowRunStatus.RETRY_WAIT}:
        return None
    await record_action(
        db,
        event_type="workflow_run_resumed",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type="workflow_run",
        entity_id=run.id,
        payload_json={"status": run.status, "current_step_index": run.current_step_index},
    )
    result = await resume_existing_workflow_run(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        run=run,
    )
    await db.commit()
    await db.refresh(result)
    return result


async def retry_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    actor_user_id: int,
    workflow_run_id: int,
) -> WorkflowRun | None:
    run = await automation_domain.get_workflow_run(db, organization_id=organization_id, workflow_run_id=workflow_run_id)
    if run is None or run.status not in {WorkflowRunStatus.FAILED, WorkflowRunStatus.PAUSED, WorkflowRunStatus.RETRY_WAIT}:
        return None
    run.retry_count += 1
    run.status = WorkflowRunStatus.RETRY_WAIT
    run.next_retry_at = compute_next_retry_at(retry_count=run.retry_count)
    run.finished_at = None
    await record_action(
        db,
        event_type="workflow_run_retry_requested",
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        entity_type="workflow_run",
        entity_id=run.id,
        payload_json={"retry_count": run.retry_count, "next_retry_at": run.next_retry_at.isoformat()},
    )
    await db.commit()
    await db.refresh(run)
    return run
