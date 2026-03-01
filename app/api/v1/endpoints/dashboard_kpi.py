"""Lightweight dashboard KPI polling endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.models.approval import Approval
from app.models.automation import AutomationTrigger, Workflow
from app.models.event import Event
from app.models.integration import Integration
from app.models.task import Task
from app.models.webhook import WebhookDelivery

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def get_dashboard_kpis(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    org_id = int(user["org_id"])
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    tasks_pending = (
        await db.execute(
            select(func.count(Task.id)).where(
                Task.organization_id == org_id, Task.is_done.is_(False)
            )
        )
    ).scalar_one()

    pending_approvals = (
        await db.execute(
            select(func.count(Approval.id)).where(
                Approval.organization_id == org_id, Approval.status == "pending"
            )
        )
    ).scalar_one()

    connected_integrations = (
        await db.execute(
            select(func.count(Integration.id)).where(
                Integration.organization_id == org_id,
                Integration.status == "connected",
            )
        )
    ).scalar_one()

    events_today = (
        await db.execute(
            select(func.count(Event.id)).where(
                Event.organization_id == org_id,
                Event.created_at >= today_start,
            )
        )
    ).scalar_one()

    active_triggers = (
        await db.execute(
            select(func.count(AutomationTrigger.id)).where(
                AutomationTrigger.organization_id == org_id,
                AutomationTrigger.is_active.is_(True),
            )
        )
    ).scalar_one()

    active_workflows = (
        await db.execute(
            select(func.count(Workflow.id)).where(
                Workflow.organization_id == org_id,
                Workflow.status == "running",
            )
        )
    ).scalar_one()

    webhook_deliveries_24h = (
        await db.execute(
            select(func.count(WebhookDelivery.id)).where(
                WebhookDelivery.organization_id == org_id,
                WebhookDelivery.created_at >= now - timedelta(hours=24),
            )
        )
    ).scalar_one()

    return {
        "tasks_pending": int(tasks_pending or 0),
        "pending_approvals": int(pending_approvals or 0),
        "connected_integrations": int(connected_integrations or 0),
        "events_today": int(events_today or 0),
        "active_triggers": int(active_triggers or 0),
        "active_workflows": int(active_workflows or 0),
        "webhook_deliveries_24h": int(webhook_deliveries_24h or 0),
        "generated_at": now.isoformat(),
    }
