from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_run import WorkflowRun, WorkflowStepRun


async def insert_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workspace_id: int | None,
    name: str,
    slug: str,
    description: str | None,
    trigger_mode: str,
    trigger_spec_json: dict,
    steps_json: list[dict],
    defaults_json: dict,
    risk_level: str,
    actor_user_id: int,
) -> WorkflowDefinition:
    row = WorkflowDefinition(
        organization_id=organization_id,
        workspace_id=workspace_id,
        name=name,
        slug=slug,
        description=description,
        trigger_mode=trigger_mode,
        trigger_spec_json=trigger_spec_json,
        steps_json=steps_json,
        defaults_json=defaults_json,
        risk_level=risk_level,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(row)
    await db.flush()
    return row


async def get_workflow_definition(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_definition_id: int,
) -> WorkflowDefinition | None:
    result = await db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_definition_id,
            WorkflowDefinition.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def list_workflow_definitions_query(
    *,
    organization_id: int,
    status: str | None = None,
) -> Select[tuple[WorkflowDefinition]]:
    query: Select[tuple[WorkflowDefinition]] = (
        select(WorkflowDefinition)
        .where(WorkflowDefinition.organization_id == organization_id)
        .order_by(WorkflowDefinition.created_at.desc())
    )
    if status:
        query = query.where(WorkflowDefinition.status == status)
    return query


async def insert_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    workspace_id: int | None,
    workflow_definition_id: int,
    workflow_version: int,
    trigger_source: str,
    trigger_signal_id: str | None,
    requested_by: int,
    started_by: int | None,
    idempotency_key: str,
    plan_snapshot_json: dict,
    input_json: dict,
    context_json: dict,
) -> WorkflowRun:
    row = WorkflowRun(
        organization_id=organization_id,
        workspace_id=workspace_id,
        workflow_definition_id=workflow_definition_id,
        workflow_version=workflow_version,
        trigger_source=trigger_source,
        trigger_signal_id=trigger_signal_id,
        requested_by=requested_by,
        started_by=started_by,
        idempotency_key=idempotency_key,
        plan_snapshot_json=plan_snapshot_json,
        input_json=input_json,
        context_json=context_json,
        last_heartbeat_at=datetime.now(UTC),
    )
    db.add(row)
    await db.flush()
    return row


async def insert_workflow_step_run(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
    step_index: int,
    step_key: str,
    action_type: str,
    idempotency_key: str,
    input_json: dict,
) -> WorkflowStepRun:
    row = WorkflowStepRun(
        organization_id=organization_id,
        workflow_run_id=workflow_run_id,
        step_index=step_index,
        step_key=step_key,
        action_type=action_type,
        idempotency_key=idempotency_key,
        input_json=input_json,
    )
    db.add(row)
    await db.flush()
    return row


async def get_workflow_run(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
) -> WorkflowRun | None:
    result = await db.execute(
        select(WorkflowRun).where(
            WorkflowRun.id == workflow_run_id,
            WorkflowRun.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def get_workflow_run_by_approval(
    db: AsyncSession,
    *,
    organization_id: int,
    approval_id: int,
) -> WorkflowRun | None:
    result = await db.execute(
        select(WorkflowRun).where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.approval_id == approval_id,
        )
    )
    return result.scalar_one_or_none()


async def get_workflow_step_run_by_approval(
    db: AsyncSession,
    *,
    organization_id: int,
    approval_id: int,
) -> WorkflowStepRun | None:
    result = await db.execute(
        select(WorkflowStepRun).where(
            WorkflowStepRun.organization_id == organization_id,
            WorkflowStepRun.approval_id == approval_id,
        )
    )
    return result.scalar_one_or_none()


async def list_workflow_runs_query(
    *,
    organization_id: int,
    status: str | None = None,
) -> Select[tuple[WorkflowRun]]:
    query: Select[tuple[WorkflowRun]] = (
        select(WorkflowRun)
        .where(WorkflowRun.organization_id == organization_id)
        .order_by(WorkflowRun.created_at.desc())
    )
    if status:
        query = query.where(WorkflowRun.status == status)
    return query


async def list_workflow_step_runs(
    db: AsyncSession,
    *,
    organization_id: int,
    workflow_run_id: int,
) -> list[WorkflowStepRun]:
    result = await db.execute(
        select(WorkflowStepRun)
        .where(
            WorkflowStepRun.organization_id == organization_id,
            WorkflowStepRun.workflow_run_id == workflow_run_id,
        )
        .order_by(WorkflowStepRun.step_index.asc())
    )
    return list(result.scalars().all())
