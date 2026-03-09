"""Role-based dashboard service — default layouts per role."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role_dashboard import RoleDashboard

DEFAULT_ROLE_LAYOUTS = {
    "CEO": [
        {"widget": "revenue_overview", "x": 0, "y": 0, "w": 6, "h": 4},
        {"widget": "deal_pipeline", "x": 6, "y": 0, "w": 6, "h": 4},
        {"widget": "team_performance", "x": 0, "y": 4, "w": 12, "h": 3},
    ],
    "ADMIN": [
        {"widget": "system_health", "x": 0, "y": 0, "w": 4, "h": 3},
        {"widget": "user_activity", "x": 4, "y": 0, "w": 4, "h": 3},
        {"widget": "integration_status", "x": 8, "y": 0, "w": 4, "h": 3},
    ],
    "MANAGER": [
        {"widget": "task_summary", "x": 0, "y": 0, "w": 6, "h": 3},
        {"widget": "contact_growth", "x": 6, "y": 0, "w": 6, "h": 3},
        {"widget": "recent_activities", "x": 0, "y": 3, "w": 12, "h": 4},
    ],
}


async def get_role_layout(
    db: AsyncSession, organization_id: int, role: str,
) -> dict:
    result = await db.execute(
        select(RoleDashboard).where(
            RoleDashboard.organization_id == organization_id,
            RoleDashboard.role == role,
        )
    )
    rd = result.scalar_one_or_none()
    if rd:
        return {"role": rd.role, "layout": json.loads(rd.layout_json), "theme": rd.theme}
    default = DEFAULT_ROLE_LAYOUTS.get(role, [])
    return {"role": role, "layout": default, "theme": "default"}


async def save_role_layout(
    db: AsyncSession, organization_id: int, role: str,
    layout: list[dict], theme: str = "default",
) -> RoleDashboard:
    result = await db.execute(
        select(RoleDashboard).where(
            RoleDashboard.organization_id == organization_id,
            RoleDashboard.role == role,
        )
    )
    rd = result.scalar_one_or_none()
    if rd:
        rd.layout_json = json.dumps(layout)
        rd.theme = theme
    else:
        rd = RoleDashboard(
            organization_id=organization_id, role=role,
            layout_json=json.dumps(layout), theme=theme,
        )
        db.add(rd)
    await db.commit()
    await db.refresh(rd)
    return rd


async def list_all_role_layouts(
    db: AsyncSession, organization_id: int,
) -> list[dict]:
    result = await db.execute(
        select(RoleDashboard).where(RoleDashboard.organization_id == organization_id)
        .order_by(RoleDashboard.role)
    )
    saved = {rd.role: {"role": rd.role, "layout": json.loads(rd.layout_json), "theme": rd.theme}
             for rd in result.scalars().all()}
    all_roles = []
    for role in ["CEO", "ADMIN", "MANAGER"]:
        if role in saved:
            all_roles.append(saved[role])
        else:
            all_roles.append({"role": role, "layout": DEFAULT_ROLE_LAYOUTS.get(role, []), "theme": "default"})
    return all_roles
