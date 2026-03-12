"""Lightweight dashboard KPI polling endpoint + layout customization."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles, require_sensitive_financial_roles
from app.models.approval import Approval
from app.models.automation import AutomationTrigger, Workflow
from app.models.event import Event
from app.models.finance import FinanceEntry
from app.models.integration import Integration
from app.models.task import Task
from app.models.webhook import WebhookDelivery
from app.services import dashboard_layout as layout_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def get_dashboard_kpis(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_sensitive_financial_roles()),
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


@router.get("/trends")
async def get_dashboard_trends(
    days: int = Query(14, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_sensitive_financial_roles()),
) -> dict:
    """Return daily time-series for revenue, tasks completed, and events."""
    org_id = int(user["org_id"])
    today = date.today()
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    labels = [d.isoformat() for d in dates]

    # Revenue per day (income - expense)
    income_rows = await db.execute(
        select(FinanceEntry.entry_date, func.sum(FinanceEntry.amount))
        .where(
            FinanceEntry.organization_id == org_id,
            FinanceEntry.type == "income",
            FinanceEntry.entry_date >= start,
        )
        .group_by(FinanceEntry.entry_date)
    )
    income_map = {r[0]: float(r[1]) for r in income_rows}

    expense_rows = await db.execute(
        select(FinanceEntry.entry_date, func.sum(FinanceEntry.amount))
        .where(
            FinanceEntry.organization_id == org_id,
            FinanceEntry.type == "expense",
            FinanceEntry.entry_date >= start,
        )
        .group_by(FinanceEntry.entry_date)
    )
    expense_map = {r[0]: float(r[1]) for r in expense_rows}

    revenue = [round(income_map.get(d, 0) - expense_map.get(d, 0), 2) for d in dates]
    income = [round(income_map.get(d, 0), 2) for d in dates]
    expenses = [round(expense_map.get(d, 0), 2) for d in dates]

    # Tasks completed per day
    tasks_rows = await db.execute(
        select(
            func.date(Task.completed_at),
            func.count(Task.id),
        )
        .where(
            Task.organization_id == org_id,
            Task.is_done.is_(True),
            Task.completed_at >= datetime(start.year, start.month, start.day, tzinfo=UTC),
        )
        .group_by(func.date(Task.completed_at))
    )
    tasks_map = {r[0]: int(r[1]) for r in tasks_rows}
    # Normalize keys — func.date may return date or str depending on dialect
    _tasks_map: dict[str, int] = {}
    for k, v in tasks_map.items():
        _tasks_map[str(k)] = v
    tasks_completed = [_tasks_map.get(d.isoformat(), 0) for d in dates]

    # Events per day
    events_rows = await db.execute(
        select(
            func.date(Event.created_at),
            func.count(Event.id),
        )
        .where(
            Event.organization_id == org_id,
            Event.created_at >= datetime(start.year, start.month, start.day, tzinfo=UTC),
        )
        .group_by(func.date(Event.created_at))
    )
    events_map: dict[str, int] = {}
    for r in events_rows:
        events_map[str(r[0])] = int(r[1])
    events = [events_map.get(d.isoformat(), 0) for d in dates]

    return {
        "labels": labels,
        "revenue": revenue,
        "income": income,
        "expenses": expenses,
        "tasks_completed": tasks_completed,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Dashboard layout customization
# ---------------------------------------------------------------------------

class WidgetPosition(BaseModel):
    id: str = Field(..., max_length=50)
    title: str = Field(..., max_length=100)
    x: int = Field(0, ge=0)
    y: int = Field(0, ge=0)
    w: int = Field(4, ge=1, le=12)
    h: int = Field(2, ge=1, le=12)


class LayoutSaveRequest(BaseModel):
    widgets: list[WidgetPosition] = Field(..., max_length=20)
    theme: str = Field("default", pattern=r"^(default|compact|dark)$")


@router.get("/layout")
async def get_layout(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> dict:
    """Get the user's saved dashboard widget layout (or defaults)."""
    return await layout_service.get_layout(db, organization_id=int(actor["org_id"]), user_id=int(actor["id"]))


@router.put("/layout")
async def save_layout(
    data: LayoutSaveRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "EMPLOYEE")),
) -> dict:
    """Save the user's dashboard widget layout."""
    widgets = [w.model_dump() for w in data.widgets]
    return await layout_service.save_layout(
        db, organization_id=int(actor["org_id"]), user_id=int(actor["id"]),
        widgets=widgets, theme=data.theme,
    )


@router.get("/anomalies")
async def get_anomalies(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_sensitive_financial_roles()),
) -> dict:
    """Run anomaly detection comparing today vs 7-day rolling averages."""
    from app.services.anomaly_detection import detect_anomalies
    org_id = int(user["org_id"])
    anomalies = await detect_anomalies(db, organization_id=org_id)
    return {"anomalies": anomalies, "count": len(anomalies)}
