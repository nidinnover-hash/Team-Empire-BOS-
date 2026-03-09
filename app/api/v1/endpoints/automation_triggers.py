"""Automation trigger CRUD endpoints (extracted from automation.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.automation import TriggerCreate, TriggerRead, TriggerUpdate
from app.services import automation as automation_service

router = APIRouter(prefix="/automations", tags=["Automations"])


@router.post("/triggers", response_model=TriggerRead, status_code=201)
async def create_trigger(
    data: TriggerCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TriggerRead:
    trigger = await automation_service.create_trigger(
        db,
        organization_id=int(actor["org_id"]),
        name=data.name, description=data.description,
        source_event=data.source_event, source_integration=data.source_integration,
        filter_json=data.filter_json, action_type=data.action_type,
        action_integration=data.action_integration, action_params=data.action_params,
        requires_approval=data.requires_approval,
    )
    await record_action(
        db, event_type="trigger_created", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="automation_trigger",
        entity_id=trigger.id, payload_json={"name": trigger.name, "source_event": trigger.source_event},
    )
    return TriggerRead.model_validate(trigger)


@router.get("/triggers", response_model=list[TriggerRead])
async def list_triggers(
    active_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[TriggerRead]:
    triggers = await automation_service.list_triggers(
        db, int(actor["org_id"]), active_only=active_only, limit=limit,
    )
    return [TriggerRead.model_validate(t) for t in triggers]


@router.get("/triggers/{trigger_id}", response_model=TriggerRead)
async def get_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> TriggerRead:
    trigger = await automation_service.get_trigger(db, trigger_id, int(actor["org_id"]))
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return TriggerRead.model_validate(trigger)


@router.patch("/triggers/{trigger_id}", response_model=TriggerRead)
async def update_trigger(
    trigger_id: int,
    data: TriggerUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> TriggerRead:
    trigger = await automation_service.update_trigger(
        db, trigger_id, int(actor["org_id"]), **data.model_dump(exclude_unset=True),
    )
    if trigger is None:
        raise HTTPException(status_code=404, detail="Trigger not found")
    await record_action(
        db, event_type="trigger_updated", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="automation_trigger",
        entity_id=trigger.id, payload_json={"name": trigger.name},
    )
    return TriggerRead.model_validate(trigger)


@router.delete("/triggers/{trigger_id}", status_code=204)
async def delete_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await automation_service.delete_trigger(db, trigger_id, int(actor["org_id"]))
    if not deleted:
        raise HTTPException(status_code=404, detail="Trigger not found")
    await record_action(
        db, event_type="trigger_deleted", actor_user_id=actor["id"],
        organization_id=actor["org_id"], entity_type="automation_trigger",
        entity_id=trigger_id, payload_json={},
    )
