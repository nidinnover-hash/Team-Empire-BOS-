"""Dashboard widget library service — CRUD for reusable widget definitions."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_widget import DashboardWidget

SYSTEM_WIDGETS = [
    {"name": "Revenue Overview", "widget_type": "chart", "data_source": "finance", "config_json": json.dumps({"chart_type": "line", "metric": "revenue"})},
    {"name": "Deal Pipeline", "widget_type": "chart", "data_source": "deals", "config_json": json.dumps({"chart_type": "funnel", "metric": "stage_count"})},
    {"name": "Task Summary", "widget_type": "metric", "data_source": "tasks", "config_json": json.dumps({"metric": "completion_rate"})},
    {"name": "Contact Growth", "widget_type": "chart", "data_source": "contacts", "config_json": json.dumps({"chart_type": "bar", "metric": "new_contacts"})},
    {"name": "Recent Activities", "widget_type": "list", "data_source": "activities", "config_json": json.dumps({"limit": 10})},
]


async def create_widget(db: AsyncSession, organization_id: int, created_by: int | None = None, **kwargs) -> DashboardWidget:
    if "config" in kwargs:
        kwargs["config_json"] = json.dumps(kwargs.pop("config"))
    widget = DashboardWidget(organization_id=organization_id, created_by_user_id=created_by, **kwargs)
    db.add(widget)
    await db.commit()
    await db.refresh(widget)
    return widget


async def list_widgets(
    db: AsyncSession, organization_id: int, widget_type: str | None = None, data_source: str | None = None,
) -> list[DashboardWidget]:
    q = select(DashboardWidget).where(
        DashboardWidget.organization_id == organization_id,
        DashboardWidget.is_active.is_(True),
    )
    if widget_type:
        q = q.where(DashboardWidget.widget_type == widget_type)
    if data_source:
        q = q.where(DashboardWidget.data_source == data_source)
    result = await db.execute(q.order_by(DashboardWidget.id))
    return list(result.scalars().all())


async def get_widget(db: AsyncSession, widget_id: int, organization_id: int) -> DashboardWidget | None:
    result = await db.execute(
        select(DashboardWidget).where(
            DashboardWidget.id == widget_id, DashboardWidget.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_widget(db: AsyncSession, widget_id: int, organization_id: int, **kwargs) -> DashboardWidget | None:
    widget = await get_widget(db, widget_id, organization_id)
    if not widget:
        return None
    if "config" in kwargs:
        kwargs["config_json"] = json.dumps(kwargs.pop("config"))
    for k, v in kwargs.items():
        if v is not None and hasattr(widget, k):
            setattr(widget, k, v)
    await db.commit()
    await db.refresh(widget)
    return widget


async def delete_widget(db: AsyncSession, widget_id: int, organization_id: int) -> bool:
    widget = await get_widget(db, widget_id, organization_id)
    if not widget:
        return False
    widget.is_active = False
    await db.commit()
    return True


async def get_system_widget_catalog() -> list[dict]:
    """Return the built-in system widget definitions."""
    return [{"index": i, **w} for i, w in enumerate(SYSTEM_WIDGETS)]
