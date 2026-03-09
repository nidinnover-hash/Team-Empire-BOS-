"""Dashboard layout service — save/load per-user widget configuration."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_layout import DEFAULT_WIDGETS, DashboardLayout


async def get_layout(
    db: AsyncSession,
    organization_id: int,
    user_id: int,
) -> dict:
    """Return the user's saved layout or the default."""
    result = await db.execute(
        select(DashboardLayout).where(
            DashboardLayout.organization_id == organization_id,
            DashboardLayout.user_id == user_id,
        )
    )
    layout = result.scalar_one_or_none()
    if layout is None:
        return {"widgets": DEFAULT_WIDGETS, "theme": "default"}
    return {"widgets": json.loads(layout.layout_json), "theme": layout.theme}


async def save_layout(
    db: AsyncSession,
    organization_id: int,
    user_id: int,
    widgets: list[dict],
    theme: str = "default",
) -> dict:
    """Upsert the user's dashboard layout."""
    result = await db.execute(
        select(DashboardLayout).where(
            DashboardLayout.organization_id == organization_id,
            DashboardLayout.user_id == user_id,
        )
    )
    layout = result.scalar_one_or_none()
    layout_str = json.dumps(widgets)

    if layout is None:
        layout = DashboardLayout(
            organization_id=organization_id,
            user_id=user_id,
            layout_json=layout_str,
            theme=theme,
        )
        db.add(layout)
    else:
        layout.layout_json = layout_str
        layout.theme = theme
        layout.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(layout)
    return {"widgets": json.loads(layout.layout_json), "theme": layout.theme}
