"""Alert engine — generates proactive notifications for budget overruns, stale contacts, failed syncs."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.notification import Notification
from app.services import notification as notification_service

logger = logging.getLogger(__name__)


async def run_alert_checks(db: AsyncSession, organization_id: int) -> dict:
    """Run all alert checks and create notifications for issues found.

    Returns a summary of alerts generated.
    """
    alerts: dict[str, int] = {}

    alerts["budget_overruns"] = await _check_budget_overruns(db, organization_id)
    alerts["stale_contacts"] = await _check_stale_contacts(db, organization_id)
    alerts["overdue_followups"] = await _check_overdue_followups(db, organization_id)
    alerts["failed_syncs"] = await _check_failed_syncs(db, organization_id)

    total = sum(alerts.values())
    logger.info("Alert checks for org %d: %d alerts generated %s", organization_id, total, alerts)
    return {"total_alerts": total, **alerts}


async def _recent_alert_exists(
    db: AsyncSession, org_id: int, alert_type: str, hours: int = 24,
) -> bool:
    """Check if an alert of this type was already created recently."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.organization_id == org_id,
            Notification.type == alert_type,
            Notification.created_at >= cutoff,
        )
    )
    return (result.scalar() or 0) > 0


async def _check_budget_overruns(db: AsyncSession, org_id: int) -> int:
    """Check for budgets where spending exceeds the limit."""
    from app.services.finance import get_budgets

    if await _recent_alert_exists(db, org_id, "budget_overrun"):
        return 0

    budgets = await get_budgets(db, organization_id=org_id)
    alerts = 0
    for budget in budgets:
        if budget.pct_used >= 90:
            severity = "high" if budget.pct_used >= 100 else "warning"
            status = "exceeded" if budget.pct_used >= 100 else "near limit"
            await notification_service.create_notification(
                db,
                organization_id=org_id,
                type="budget_overrun",
                severity=severity,
                title=f"Budget {status}: {budget.category}",
                message=f"{budget.category} budget is at {budget.pct_used}% "
                        f"(${budget.spent_this_month:.2f} of ${budget.monthly_limit:.2f})",
                source="alert_engine",
                entity_type="budget",
            )
            alerts += 1
    return alerts


async def _check_stale_contacts(db: AsyncSession, org_id: int) -> int:
    """Check for high-value contacts with no activity in 30+ days."""
    if await _recent_alert_exists(db, org_id, "stale_contact"):
        return 0

    cutoff = datetime.now(UTC) - timedelta(days=30)
    result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.organization_id == org_id,
            Contact.lead_score >= 50,
            Contact.pipeline_stage.notin_(["won", "lost"]),
            (Contact.last_contacted_at < cutoff) | (Contact.last_contacted_at.is_(None)),
        )
    )
    stale_count = result.scalar() or 0

    if stale_count > 0:
        await notification_service.create_notification(
            db,
            organization_id=org_id,
            type="stale_contact",
            severity="warning",
            title=f"{stale_count} high-value contacts going stale",
            message=f"{stale_count} contacts with lead score >= 50 have had no activity in 30+ days.",
            source="alert_engine",
            entity_type="contact",
        )
        return 1
    return 0


async def _check_overdue_followups(db: AsyncSession, org_id: int) -> int:
    """Check for overdue follow-ups."""
    if await _recent_alert_exists(db, org_id, "overdue_followup"):
        return 0

    now = datetime.now(UTC)
    result = await db.execute(
        select(func.count(Contact.id)).where(
            Contact.organization_id == org_id,
            Contact.next_follow_up_at < now,
            Contact.pipeline_stage.notin_(["won", "lost"]),
        )
    )
    overdue = result.scalar() or 0

    if overdue >= 3:
        await notification_service.create_notification(
            db,
            organization_id=org_id,
            type="overdue_followup",
            severity="warning",
            title=f"{overdue} overdue follow-ups",
            message=f"You have {overdue} contacts with overdue follow-up dates. Review your pipeline.",
            source="alert_engine",
            entity_type="contact",
        )
        return 1
    return 0


async def _check_failed_syncs(db: AsyncSession, org_id: int) -> int:
    """Check for integrations with sync errors."""
    from app.models.integration import Integration

    if await _recent_alert_exists(db, org_id, "failed_sync"):
        return 0

    result = await db.execute(
        select(Integration).where(
            Integration.organization_id == org_id,
            Integration.status == "connected",
            Integration.sync_error_count >= 3,
        )
    )
    failing = list(result.scalars().all())

    alerts = 0
    for integration in failing:
        await notification_service.create_notification(
            db,
            organization_id=org_id,
            type="failed_sync",
            severity="high",
            title=f"Integration sync failing: {integration.integration_type}",
            message=f"{integration.integration_type} has failed {integration.sync_error_count} "
                    f"consecutive syncs. Check connection and credentials.",
            source="alert_engine",
            entity_type="integration",
            entity_id=integration.id,
        )
        alerts += 1
    return alerts
