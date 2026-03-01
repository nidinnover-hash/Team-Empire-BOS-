"""Service layer for automation triggers and multi-step workflows."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationTrigger, Workflow

logger = logging.getLogger(__name__)

_STEP_TIMEOUT_SECONDS = 30


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Automation Triggers ──────────────────────────────────────────────────────


async def create_trigger(
    db: AsyncSession,
    organization_id: int,
    *,
    name: str,
    source_event: str,
    action_type: str,
    description: str | None = None,
    source_integration: str | None = None,
    filter_json: dict | None = None,
    action_integration: str | None = None,
    action_params: dict | None = None,
    requires_approval: bool = False,
) -> AutomationTrigger:
    trigger = AutomationTrigger(
        organization_id=organization_id,
        name=name,
        description=description,
        source_event=source_event,
        source_integration=source_integration,
        filter_json=filter_json or {},
        action_type=action_type,
        action_integration=action_integration,
        action_params=action_params or {},
        requires_approval=requires_approval,
    )
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)
    return trigger


async def list_triggers(
    db: AsyncSession,
    organization_id: int,
    active_only: bool = False,
    limit: int = 100,
) -> list[AutomationTrigger]:
    q = select(AutomationTrigger).where(
        AutomationTrigger.organization_id == organization_id
    )
    if active_only:
        q = q.where(AutomationTrigger.is_active.is_(True))
    q = q.order_by(AutomationTrigger.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_trigger(
    db: AsyncSession, trigger_id: int, organization_id: int
) -> AutomationTrigger | None:
    result = await db.execute(
        select(AutomationTrigger).where(
            AutomationTrigger.id == trigger_id,
            AutomationTrigger.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_trigger(
    db: AsyncSession,
    trigger_id: int,
    organization_id: int,
    **kwargs: object,
) -> AutomationTrigger | None:
    trigger = await get_trigger(db, trigger_id, organization_id)
    if trigger is None:
        return None
    for key, value in kwargs.items():
        if value is not None and hasattr(trigger, key):
            setattr(trigger, key, value)
    await db.commit()
    await db.refresh(trigger)
    return trigger


async def delete_trigger(
    db: AsyncSession, trigger_id: int, organization_id: int
) -> bool:
    trigger = await get_trigger(db, trigger_id, organization_id)
    if trigger is None:
        return False
    await db.delete(trigger)
    await db.commit()
    return True


async def fire_matching_triggers(
    db: AsyncSession,
    organization_id: int,
    event_type: str,
    event_payload: dict | None = None,
) -> list[AutomationTrigger]:
    """Find all active triggers matching this event and return them.

    The actual action execution is left to the caller (endpoint or scheduler)
    so we can respect the requires_approval flag.
    """
    result = await db.execute(
        select(AutomationTrigger).where(
            AutomationTrigger.organization_id == organization_id,
            AutomationTrigger.is_active.is_(True),
            AutomationTrigger.source_event == event_type,
        )
    )
    triggers = list(result.scalars().all())
    matched: list[AutomationTrigger] = []
    for t in triggers:
        # Optional filter matching (simple key-value subset check)
        if t.filter_json and event_payload and not all(
            event_payload.get(k) == v for k, v in t.filter_json.items()
        ):
            continue
        t.fire_count += 1
        t.last_fired_at = datetime.now(UTC)
        matched.append(t)
    if matched:
        await db.commit()
    return matched


# ── Multi-step Workflows ─────────────────────────────────────────────────────


async def create_workflow(
    db: AsyncSession,
    organization_id: int,
    *,
    name: str,
    steps_json: list,
    description: str | None = None,
    created_by: int | None = None,
) -> Workflow:
    wf = Workflow(
        organization_id=organization_id,
        name=name,
        description=description,
        steps_json=steps_json,
        created_by=created_by,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


async def list_workflows(
    db: AsyncSession,
    organization_id: int,
    status: str | None = None,
    limit: int = 100,
) -> list[Workflow]:
    q = select(Workflow).where(Workflow.organization_id == organization_id)
    if status:
        q = q.where(Workflow.status == status)
    q = q.order_by(Workflow.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_workflow(
    db: AsyncSession, workflow_id: int, organization_id: int
) -> Workflow | None:
    result = await db.execute(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def start_workflow(
    db: AsyncSession, workflow_id: int, organization_id: int
) -> Workflow | None:
    wf = await get_workflow(db, workflow_id, organization_id)
    if wf is None or wf.status not in (WorkflowStatus.DRAFT, WorkflowStatus.PAUSED):
        return None
    wf.status = WorkflowStatus.RUNNING
    wf.started_at = datetime.now(UTC)
    wf.current_step = 0
    await db.commit()
    await db.refresh(wf)
    return wf


async def advance_workflow(
    db: AsyncSession,
    workflow_id: int,
    organization_id: int,
    step_result: dict | None = None,
) -> Workflow | None:
    """Mark current step complete and advance to next. Returns None if not found."""
    wf = await get_workflow(db, workflow_id, organization_id)
    if wf is None or wf.status != WorkflowStatus.RUNNING:
        return None
    # Create new dict to ensure SQLAlchemy detects JSON mutation
    results = dict(wf.result_json or {})
    results[f"step_{wf.current_step}"] = step_result or {}
    wf.result_json = results
    wf.current_step += 1
    if wf.current_step >= len(wf.steps_json):
        wf.status = WorkflowStatus.COMPLETED
        wf.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(wf)
    return wf


async def fail_workflow(
    db: AsyncSession,
    workflow_id: int,
    organization_id: int,
    error_text: str,
) -> Workflow | None:
    wf = await get_workflow(db, workflow_id, organization_id)
    if wf is None:
        return None
    wf.status = WorkflowStatus.FAILED
    wf.error_text = error_text
    wf.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(wf)
    return wf


# ── Workflow Step Executor ──────────────────────────────────────────────────


def _get_step_handlers() -> dict[str, Callable[..., Any]]:
    """Lazily import execution_engine HANDLERS to avoid circular imports."""
    from app.services.execution_engine import HANDLERS

    return HANDLERS


async def _run_step_handler(
    handler: Callable[..., Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    """Run a step handler (sync or async) with timeout."""
    if asyncio.iscoroutinefunction(handler) or inspect.isasyncgenfunction(handler):
        result = await asyncio.wait_for(handler(params), timeout=_STEP_TIMEOUT_SECONDS)
    else:
        result = handler(params)
        if asyncio.iscoroutine(result):
            result = await asyncio.wait_for(result, timeout=_STEP_TIMEOUT_SECONDS)
    if not isinstance(result, dict):
        return {"output": str(result)}
    return result


async def execute_current_step(
    db: AsyncSession,
    workflow_id: int,
    organization_id: int,
) -> Workflow | None:
    """Execute the current step of a running workflow, then advance or fail.

    Steps have an ``action_type`` that maps to a handler in execution_engine.
    If no handler exists, the step is auto-advanced with a ``skipped`` result.
    """
    wf = await get_workflow(db, workflow_id, organization_id)
    if wf is None or wf.status != WorkflowStatus.RUNNING:
        return wf

    if wf.current_step >= len(wf.steps_json):
        wf.status = WorkflowStatus.COMPLETED
        wf.finished_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(wf)
        return wf

    step = wf.steps_json[wf.current_step]
    action_type = step.get("action_type", "")
    params = step.get("params") or {}
    handlers = _get_step_handlers()
    handler = handlers.get(action_type)

    if handler is None:
        # No handler — auto-advance with skip note
        return await advance_workflow(
            db, workflow_id, organization_id,
            step_result={"status": "skipped", "reason": f"no handler for {action_type}"},
        )

    try:
        output = await _run_step_handler(handler, params)
        return await advance_workflow(
            db, workflow_id, organization_id,
            step_result={"status": "succeeded", "output": output},
        )
    except TimeoutError:
        return await fail_workflow(
            db, workflow_id, organization_id,
            error_text=f"Step {wf.current_step} ({action_type}) timed out after {_STEP_TIMEOUT_SECONDS}s",
        )
    except Exception as exc:
        return await fail_workflow(
            db, workflow_id, organization_id,
            error_text=f"Step {wf.current_step} ({action_type}) failed: {type(exc).__name__}: {str(exc)[:200]}",
        )


async def run_workflow(
    db: AsyncSession,
    workflow_id: int,
    organization_id: int,
) -> Workflow | None:
    """Execute all remaining steps of a workflow sequentially."""
    wf = await get_workflow(db, workflow_id, organization_id)
    if wf is None:
        return None

    if wf.status in (WorkflowStatus.DRAFT, WorkflowStatus.PAUSED):
        wf = await start_workflow(db, workflow_id, organization_id)
        if wf is None:
            return None

    while wf and wf.status == WorkflowStatus.RUNNING:
        wf = await execute_current_step(db, workflow_id, organization_id)

    return wf
