from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import notification as notification_service

logger = logging.getLogger(__name__)


async def send_pending_alert(
    db: AsyncSession,
    *,
    org_id: int,
    entity_type: str,
    entity_id: int,
    title: str,
    detail: str,
) -> None:
    """Create in-app notification + best-effort Slack for pending alerts."""
    # 1. In-app notification (always)
    await notification_service.create_notification(
        db,
        organization_id=org_id,
        type="alert",
        severity="warning",
        title=title,
        message=detail,
        source="alert_service",
        entity_type=entity_type,
        entity_id=entity_id,
    )
    await db.commit()

    # 2. Slack (best-effort, fire-and-forget)
    try:
        from app.core.config import settings

        channel_id = (settings.CEO_ALERTS_SLACK_CHANNEL_ID or "").strip()
        if channel_id:
            from app.services import slack_service

            await slack_service.send_to_slack(
                db, org_id, channel_id, f"*{title}*\n{detail}"
            )
    except Exception as exc:
        logger.debug("Alert Slack delivery failed: %s", type(exc).__name__)
