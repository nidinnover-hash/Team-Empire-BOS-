"""Notification preference service — CRUD for per-user notification settings."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_preference import NotificationPreference

logger = logging.getLogger(__name__)

# Default categories users can configure
EVENT_CATEGORIES = [
    "task", "approval", "deal", "contact", "finance",
    "integration", "alert", "email", "automation", "system",
]


async def list_preferences(
    db: AsyncSession, user_id: int, organization_id: int,
) -> list[NotificationPreference]:
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.organization_id == organization_id,
        ).order_by(NotificationPreference.event_category)
    )
    return list(result.scalars().all())


async def get_preferences_with_defaults(
    db: AsyncSession, user_id: int, organization_id: int,
) -> list[dict]:
    """Return all categories with user overrides merged with defaults."""
    existing = await list_preferences(db, user_id, organization_id)
    existing_map = {p.event_category: p for p in existing}

    result = []
    for cat in EVENT_CATEGORIES:
        if cat in existing_map:
            p = existing_map[cat]
            result.append({
                "event_category": cat,
                "in_app": p.in_app,
                "email": p.email,
                "slack": p.slack,
                "min_severity": p.min_severity,
                "muted": p.muted,
            })
        else:
            result.append({
                "event_category": cat,
                "in_app": True,
                "email": False,
                "slack": False,
                "min_severity": "info",
                "muted": False,
            })
    return result


async def upsert_preference(
    db: AsyncSession,
    user_id: int,
    organization_id: int,
    event_category: str,
    *,
    in_app: bool | None = None,
    email: bool | None = None,
    slack: bool | None = None,
    min_severity: str | None = None,
    muted: bool | None = None,
) -> NotificationPreference:
    """Create or update a notification preference for one category."""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.organization_id == organization_id,
            NotificationPreference.event_category == event_category,
        )
    )
    pref = result.scalar_one_or_none()

    if pref is None:
        pref = NotificationPreference(
            user_id=user_id,
            organization_id=organization_id,
            event_category=event_category,
        )
        db.add(pref)

    if in_app is not None:
        pref.in_app = in_app
    if email is not None:
        pref.email = email
    if slack is not None:
        pref.slack = slack
    if min_severity is not None:
        pref.min_severity = min_severity
    if muted is not None:
        pref.muted = muted

    pref.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(pref)
    return pref


async def should_notify(
    db: AsyncSession, user_id: int, organization_id: int,
    event_category: str, severity: str = "info",
) -> dict:
    """Check if a user should be notified for this category/severity.

    Returns dict with channel flags: {in_app, email, slack}.
    """
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.organization_id == organization_id,
            NotificationPreference.event_category == event_category,
        )
    )
    pref = result.scalar_one_or_none()

    if pref is None:
        return {"in_app": True, "email": False, "slack": False}

    if pref.muted:
        return {"in_app": False, "email": False, "slack": False}

    severity_order = {"info": 0, "warning": 1, "critical": 2}
    min_level = severity_order.get(pref.min_severity, 0)
    current_level = severity_order.get(severity, 0)

    if current_level < min_level:
        return {"in_app": False, "email": False, "slack": False}

    return {"in_app": pref.in_app, "email": pref.email, "slack": pref.slack}
