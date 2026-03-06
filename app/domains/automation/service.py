from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.automation import repo
from app.domains.automation.events import emit_workflow_signal
from app.domains.automation.models import (
    WorkflowDefinitionStatus,
    WorkflowRunStatus,
    WorkflowStepRunStatus,
    normalize_slug,
    normalize_steps,
)
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_run import WorkflowRun, WorkflowStepRun
from app.platform.signals.topics import (
    WORKFLOW_DEFINITION_CREATED,
    WORKFLOW_DEFINITION_PUBLISHED,
    WORKFLOW_DEFINITION_UPDATED,
    WORKFLOW_RUN_AWAITING_APPROVAL,
    WORKFLOW_RUN_COMPLETED,
    WORKFLOW_RUN_CREATED,
    WORKFLOW_RUN_FAILED,
    WORKFLOW_RUN_STARTED,
    WORKFLOW_STEP_COMPLETED,
    WORKFLOW_STEP_FAILED,
    WORKFLOW_STEP_STARTED,
)


async def create_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workspace_id: int | None,
    actor_user_id: int,
    name: str,
    description: str | None,
    trigger_mode: str,
    trigger_spec_json: dict | None,
    steps_json: list[dict],
    defaults_json: dict | None,
    risk_level: str,
) -> WorkflowDefinition:
    row = await repo.insert_workflow_definition(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        name=name,
        slug=normalize_slug(name),
        description=description,
        trigger_mode=trigger_mode,
        trigger_spec_json=trigger_spec_json or {},
        steps_json=normalize_steps(steps_json),
        defaults_json=defaults_json or {},
        risk_level=risk_level,
        actor_user_id=actor_user_id,
    )
    await emit_workflow_signal(
        topic=WORKFLOW_DEFINITION_CREATED,
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_definition",
        entity_id=str(row.id),
        payload={"workflow_definition_id": row.id, "status": row.status, "version": row.version},
        source="domains.automation.service",
        db=db,
    )
    return row


async def list_workflow_definitions(
    db: AsyncSession,
    *,
    organization_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[WorkflowDefinition]:
    result = await db.execute((await repo.list_workflow_definitions_query(organization_id=organization_id, status=status)).limit(limit))
    return list(result.scalars().all())


async def get_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_definition_id: int,
) -> WorkflowDefinition | None:
    return await repo.get_workflow_definition(db, organization_id=organization_id, workflow_definition_id=workflow_definition_id)


async def update_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_definition_id: int,
    actor_user_id: int,
    name: str | None = None,
    description: str | None = None,
    trigger_mode: str | None = None,
    trigger_spec_json: dict | None = None,
    steps_json: list[dict] | None = None,
    defaults_json: dict | None = None,
    risk_level: str | None = None,
) -> WorkflowDefinition | None:
    row = await repo.get_workflow_definition(db, organization_id=organization_id, workflow_definition_id=workflow_definition_id)
    if row is None or row.status == WorkflowDefinitionStatus.ARCHIVED:
        return None
    if name is not None:
        row.name = name
        row.slug = normalize_slug(name)
    if description is not None:
        row.description = description
    if trigger_mode is not None:
        row.trigger_mode = trigger_mode
    if trigger_spec_json is not None:
        row.trigger_spec_json = dict(trigger_spec_json)
    if steps_json is not None:
        row.steps_json = normalize_steps(steps_json)
    if defaults_json is not None:
        row.defaults_json = dict(defaults_json)
    if risk_level is not None:
        row.risk_level = risk_level
    row.updated_by = actor_user_id
    row.updated_at = datetime.now(UTC)
    await emit_workflow_signal(
        topic=WORKFLOW_DEFINITION_UPDATED,
        organization_id=organization_id,
        workspace_id=row.workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_definition",
        entity_id=str(row.id),
        payload={"workflow_definition_id": row.id, "status": row.status, "version": row.version},
        source="domains.automation.service",
        db=db,
    )
    return row


async def publish_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_definition_id: int,
    actor_user_id: int,
) -> WorkflowDefinition | None:
    row = await repo.get_workflow_definition(db, organization_id=organization_id, workflow_definition_id=workflow_definition_id)
    if row is None:
        return None
    if row.status == WorkflowDefinitionStatus.ARCHIVED:
        raise ValueError("Archived workflow definitions cannot be published")
    row.status = WorkflowDefinitionStatus.PUBLISHED
    row.version = int(row.version or 1) + 1
    row.updated_by = actor_user_id
    row.published_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    await emit_workflow_signal(
        topic=WORKFLOW_DEFINITION_PUBLISHED,
        organization_id=organization_id,
        workspace_id=row.workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_definition",
        entity_id=str(row.id),
        payload={"workflow_definition_id": row.id, "status": row.status, "version": row.version},
        source="domains.automation.service",
        db=db,
    )
    return row


async def create_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    workspace_id: int | None,
    actor_user_id: int,
    definition: WorkflowDefinition,
    trigger_source: str,
    trigger_signal_id: str | None,
    idempotency_key: str,
    input_json: dict,
    context_json: dict,
    plan_snapshot_json: dict,
) -> tuple[WorkflowRun, list[WorkflowStepRun]]:
    existing = (
        await db.execute(
            select(WorkflowRun).where(
                WorkflowRun.organization_id == organization_id,
                WorkflowRun.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        steps = await repo.list_workflow_step_runs(db, organization_id=organization_id, workflow_run_id=existing.id)
        return existing, steps
    run = await repo.insert_workflow_run(
        db,
        organization_id=organization_id,
        workspace_id=workspace_id,
        workflow_definition_id=definition.id,
        workflow_version=definition.version,
        trigger_source=trigger_source,
        trigger_signal_id=trigger_signal_id,
        requested_by=actor_user_id,
        started_by=actor_user_id,
        idempotency_key=idempotency_key,
        plan_snapshot_json=plan_snapshot_json,
        input_json=input_json,
        context_json=context_json,
    )
    step_rows: list[WorkflowStepRun] = []
    for index, step in enumerate(definition.steps_json or []):
        step_rows.append(
            await repo.insert_workflow_step_run(
                db,
                organization_id=organization_id,
                workflow_run_id=run.id,
                step_index=index,
                step_key=str(step.get("key") or f"step-{index + 1}"),
                action_type=str(step.get("action_type") or ""),
                idempotency_key=f"workflow-run:{run.id}:step:{index}:attempt:1",
                input_json=dict(step.get("params") or {}),
            )
        )
    await emit_workflow_signal(
        topic=WORKFLOW_RUN_CREATED,
        organization_id=organization_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={"workflow_run_id": run.id, "workflow_definition_id": definition.id, "trigger_source": trigger_source},
        source="domains.automation.service",
        db=db,
    )
    return run, step_rows


async def list_workflow_runs(
    db: AsyncSession,
    *,
    organization_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[WorkflowRun]:
    result = await db.execute((await repo.list_workflow_runs_query(organization_id=organization_id, status=status)).limit(limit))
    return list(result.scalars().all())


async def get_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
) -> WorkflowRun | None:
    return await repo.get_workflow_run(db, organization_id=organization_id, workflow_run_id=workflow_run_id)


async def get_workflow_step_runs(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
) -> list[WorkflowStepRun]:
    return await repo.list_workflow_step_runs(db, organization_id=organization_id, workflow_run_id=workflow_run_id)


async def mark_run_started(db: AsyncSession, *, run: WorkflowRun, actor_user_id: int) -> WorkflowRun:
    run.status = WorkflowRunStatus.RUNNING
    run.started_by = actor_user_id
    run.started_at = run.started_at or datetime.now(UTC)
    run.last_heartbeat_at = datetime.now(UTC)
    await emit_workflow_signal(
        topic=WORKFLOW_RUN_STARTED,
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={"workflow_run_id": run.id, "workflow_definition_id": run.workflow_definition_id},
        source="domains.automation.service",
        db=db,
    )
    return run


async def mark_run_awaiting_approval(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    actor_user_id: int,
    approval_id: int,
    step_index: int,
) -> WorkflowRun:
    run.status = WorkflowRunStatus.AWAITING_APPROVAL
    run.approval_id = approval_id
    run.current_step_index = step_index
    run.last_heartbeat_at = datetime.now(UTC)
    await emit_workflow_signal(
        topic=WORKFLOW_RUN_AWAITING_APPROVAL,
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={"workflow_run_id": run.id, "approval_id": approval_id, "step_index": step_index},
        source="domains.automation.service",
        db=db,
    )
    return run


async def mark_run_completed(db: AsyncSession, *, run: WorkflowRun, actor_user_id: int) -> WorkflowRun:
    run.status = WorkflowRunStatus.COMPLETED
    run.finished_at = datetime.now(UTC)
    run.last_heartbeat_at = datetime.now(UTC)
    await emit_workflow_signal(
        topic=WORKFLOW_RUN_COMPLETED,
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={"workflow_run_id": run.id, "workflow_definition_id": run.workflow_definition_id},
        source="domains.automation.service",
        db=db,
    )
    return run


async def mark_run_failed(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    actor_user_id: int | None,
    error_summary: str,
) -> WorkflowRun:
    run.status = WorkflowRunStatus.FAILED
    run.error_summary = error_summary
    run.finished_at = datetime.now(UTC)
    run.last_heartbeat_at = datetime.now(UTC)
    await emit_workflow_signal(
        topic=WORKFLOW_RUN_FAILED,
        organization_id=run.organization_id,
        workspace_id=run.workspace_id,
        actor_user_id=actor_user_id,
        entity_type="workflow_run",
        entity_id=str(run.id),
        payload={"workflow_run_id": run.id, "error_summary": error_summary},
        source="domains.automation.service",
        db=db,
    )
    return run


async def mark_step_started(db: AsyncSession, *, step_run: WorkflowStepRun, actor_user_id: int, workflow_run_id: int) -> WorkflowStepRun:
    step_run.status = WorkflowStepRunStatus.RUNNING
    step_run.attempt_count += 1
    step_run.started_at = datetime.now(UTC)
    await emit_workflow_signal(
        topic=WORKFLOW_STEP_STARTED,
        organization_id=step_run.organization_id,
        workspace_id=None,
        actor_user_id=actor_user_id,
        entity_type="workflow_step_run",
        entity_id=str(step_run.id),
        payload={"workflow_run_id": workflow_run_id, "workflow_step_run_id": step_run.id, "step_index": step_run.step_index},
        source="domains.automation.service",
        db=db,
    )
    return step_run


async def mark_step_completed(
    db: AsyncSession,
    *,
    step_run: WorkflowStepRun,
    actor_user_id: int,
    workflow_run_id: int,
    output_json: dict,
    execution_id: int,
    approval_id: int,
    status: str,
) -> WorkflowStepRun:
    step_run.status = status
    step_run.output_json = output_json
    step_run.execution_id = execution_id
    step_run.approval_id = approval_id
    step_run.finished_at = datetime.now(UTC)
    if step_run.started_at is not None:
        step_run.latency_ms = max(0, int((step_run.finished_at - step_run.started_at).total_seconds() * 1000))
    await emit_workflow_signal(
        topic=WORKFLOW_STEP_COMPLETED,
        organization_id=step_run.organization_id,
        workspace_id=None,
        actor_user_id=actor_user_id,
        entity_type="workflow_step_run",
        entity_id=str(step_run.id),
        payload={
            "workflow_run_id": workflow_run_id,
            "workflow_step_run_id": step_run.id,
            "step_index": step_run.step_index,
            "execution_id": execution_id,
            "approval_id": approval_id,
            "status": status,
        },
        source="domains.automation.service",
        db=db,
    )
    return step_run


async def mark_step_failed(
    db: AsyncSession,
    *,
    step_run: WorkflowStepRun,
    actor_user_id: int | None,
    workflow_run_id: int,
    error_text: str,
    execution_id: int | None = None,
    approval_id: int | None = None,
) -> WorkflowStepRun:
    step_run.status = WorkflowStepRunStatus.FAILED
    step_run.error_text = error_text
    step_run.execution_id = execution_id
    step_run.approval_id = approval_id
    step_run.finished_at = datetime.now(UTC)
    if step_run.started_at is not None:
        step_run.latency_ms = max(0, int((step_run.finished_at - step_run.started_at).total_seconds() * 1000))
    await emit_workflow_signal(
        topic=WORKFLOW_STEP_FAILED,
        organization_id=step_run.organization_id,
        workspace_id=None,
        actor_user_id=actor_user_id,
        entity_type="workflow_step_run",
        entity_id=str(step_run.id),
        payload={
            "workflow_run_id": workflow_run_id,
            "workflow_step_run_id": step_run.id,
            "step_index": step_run.step_index,
            "execution_id": execution_id,
            "approval_id": approval_id,
            "error_text": error_text,
        },
        source="domains.automation.service",
        db=db,
    )
    return step_run
