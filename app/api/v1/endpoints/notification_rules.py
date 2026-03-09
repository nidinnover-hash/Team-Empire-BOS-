"""Notification rules — configurable event-to-notification routing."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import notification_rule as rule_service

router = APIRouter(prefix="/notification-rules", tags=["Notification Rules"])


class NotificationRuleCreate(BaseModel):
    name: str = Field(..., max_length=200)
    event_type_pattern: str = Field(..., max_length=100)  # e.g. "deal_*", "task_created"
    severity: str = Field("info", pattern=r"^(info|warning|critical)$")
    channel: str = Field("in_app", pattern=r"^(in_app|email|both)$")
    target_roles: str = Field("CEO,ADMIN", max_length=200)
    target_user_id: int | None = None
    description: str | None = None


class NotificationRuleUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    event_type_pattern: str | None = None
    severity: str | None = Field(None, pattern=r"^(info|warning|critical)$")
    channel: str | None = Field(None, pattern=r"^(in_app|email|both)$")
    target_roles: str | None = None
    target_user_id: int | None = None
    is_active: bool | None = None
    description: str | None = None


class NotificationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    event_type_pattern: str
    severity: str
    channel: str
    target_roles: str
    target_user_id: int | None = None
    is_active: bool
    description: str | None = None
    created_at: datetime | None = None


@router.get("", response_model=list[NotificationRuleRead])
async def list_notification_rules(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[NotificationRuleRead]:
    rules = await rule_service.list_rules(db, organization_id=actor["org_id"], active_only=active_only)
    return [NotificationRuleRead.model_validate(r, from_attributes=True) for r in rules]


@router.post("", response_model=NotificationRuleRead, status_code=201)
async def create_notification_rule(
    data: NotificationRuleCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> NotificationRuleRead:
    rule = await rule_service.create_rule(
        db, organization_id=actor["org_id"],
        name=data.name, event_type_pattern=data.event_type_pattern,
        severity=data.severity, channel=data.channel,
        target_roles=data.target_roles, target_user_id=data.target_user_id,
        description=data.description,
    )
    return NotificationRuleRead.model_validate(rule, from_attributes=True)


@router.patch("/{rule_id}", response_model=NotificationRuleRead)
async def update_notification_rule(
    rule_id: int,
    data: NotificationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> NotificationRuleRead:
    rule = await rule_service.update_rule(
        db, rule_id=rule_id, organization_id=actor["org_id"],
        **data.model_dump(exclude_unset=True),
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return NotificationRuleRead.model_validate(rule, from_attributes=True)


@router.delete("/{rule_id}", status_code=204)
async def delete_notification_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await rule_service.delete_rule(db, rule_id=rule_id, organization_id=actor["org_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")


@router.get("/evaluate")
async def evaluate_event(
    event_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict:
    """Evaluate which notification rules match a given event type."""
    matched = await rule_service.evaluate_event(db, organization_id=actor["org_id"], event_type=event_type)
    return {"event_type": event_type, "matched_rules": matched}
