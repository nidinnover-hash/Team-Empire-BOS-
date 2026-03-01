"""Service layer for automation triggers and multi-step workflows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import AutomationTrigger, Workflow

logger = logging.getLogger(__name__)


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
    triggers = await list_triggers(db, organization_id, active_only=True)
    matched: list[AutomationTrigger] = []
    for t in triggers:
        if t.source_event != event_type:
            continue
        # Optional filter matching (simple key-value subset check)
        if t.filter_json and event_payload:
            if not all(
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
    if wf is None or wf.status not in ("draft", "paused"):
        return None
    wf.status = "running"
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
    if wf is None or wf.status != "running":
        return None
    results = wf.result_json or {}
    results[f"step_{wf.current_step}"] = step_result or {}
    wf.result_json = results
    wf.current_step += 1
    if wf.current_step >= len(wf.steps_json):
        wf.status = "completed"
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
    wf.status = "failed"
    wf.error_text = error_text
    wf.finished_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(wf)
    return wf
