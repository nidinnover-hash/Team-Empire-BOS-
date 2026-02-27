from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.approval import Approval
from app.models.integration import Integration
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.user import User
from app.schemas.admin import OrgReadinessMetric, OrgReadinessReport


def _metric_status(
    value: int,
    *,
    target: int,
    reverse: bool = False,
) -> Literal["ok", "warning", "critical"]:
    if reverse:
        if value == 0:
            return "ok"
        if value <= target:
            return "warning"
        return "critical"
    if value >= target:
        return "ok"
    if value >= max(0, target - 1):
        return "warning"
    return "critical"


async def build_org_readiness_report(db: AsyncSession, org: Organization) -> OrgReadinessReport:
    org_id = int(org.id)
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(hours=int(settings.SYNC_STALE_HOURS))
    approval_cutoff = now - timedelta(hours=int(settings.APPROVAL_SLA_HOURS))

    active_user_count = int(
        (
            await db.execute(
                select(func.count(User.id)).where(
                    User.organization_id == org_id,
                    User.is_active.is_(True),
                )
            )
        ).scalar_one()
        or 0
    )
    connected_integrations = int(
        (
            await db.execute(
                select(func.count(Integration.id)).where(
                    Integration.organization_id == org_id,
                    Integration.status == "connected",
                )
            )
        ).scalar_one()
        or 0
    )
    stale_integrations = int(
        (
            await db.execute(
                select(func.count(Integration.id)).where(
                    Integration.organization_id == org_id,
                    Integration.status == "connected",
                    (
                        (Integration.last_sync_at.is_(None))
                        | (Integration.last_sync_at < stale_cutoff)
                        | (Integration.last_sync_status == "error")
                    ),
                )
            )
        ).scalar_one()
        or 0
    )
    pending_approvals = int(
        (
            await db.execute(
                select(func.count(Approval.id)).where(
                    Approval.organization_id == org_id,
                    Approval.status == "pending",
                )
            )
        ).scalar_one()
        or 0
    )
    sla_breached_approvals = int(
        (
            await db.execute(
                select(func.count(Approval.id)).where(
                    Approval.organization_id == org_id,
                    Approval.status == "pending",
                    Approval.created_at < approval_cutoff,
                )
            )
        ).scalar_one()
        or 0
    )
    unread_high_alerts = int(
        (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.organization_id == org_id,
                    Notification.is_read.is_(False),
                    Notification.severity.in_(["high", "error", "critical"]),
                )
            )
        ).scalar_one()
        or 0
    )

    score = 100
    blockers: list[str] = []
    recommendations: list[str] = []

    if active_user_count < 2:
        score -= 15
        recommendations.append("Add at least one additional active operator account.")
    if connected_integrations == 0:
        score -= 35
        blockers.append("No connected integrations. Connect at least one core system (GitHub/ClickUp/Slack).")
    elif connected_integrations == 1:
        score -= 15
        recommendations.append("Connect more systems to improve execution context depth.")
    if stale_integrations > 0:
        score -= min(25, stale_integrations * 8)
        if stale_integrations >= 2:
            blockers.append("Multiple integrations are stale or failing sync health checks.")
        else:
            recommendations.append("Resolve stale integration sync status before scaling autonomy.")
    if sla_breached_approvals > 0:
        score -= min(30, sla_breached_approvals * 6)
        if sla_breached_approvals >= 3:
            blockers.append("Approval queue SLA is breached for multiple pending decisions.")
        else:
            recommendations.append("Clear overdue approvals to restore decision latency targets.")
    if unread_high_alerts > 0:
        score -= min(20, unread_high_alerts * 4)
        recommendations.append("Triage unread high-severity alerts.")
    if pending_approvals > 20:
        score -= 10
        recommendations.append("Reduce pending approvals backlog to keep execution unblocked.")

    score = max(0, min(100, int(score)))
    if blockers:
        status: Literal["ready", "watch", "blocked"] = "blocked"
    elif score >= 80:
        status = "ready"
    else:
        status = "watch"

    metrics = [
        OrgReadinessMetric(
            name="active_users",
            value=active_user_count,
            target=2,
            status=_metric_status(active_user_count, target=2),
        ),
        OrgReadinessMetric(
            name="connected_integrations",
            value=connected_integrations,
            target=2,
            status=_metric_status(connected_integrations, target=2),
        ),
        OrgReadinessMetric(
            name="stale_integrations",
            value=stale_integrations,
            target=1,
            status=_metric_status(stale_integrations, target=1, reverse=True),
        ),
        OrgReadinessMetric(
            name="pending_approvals_sla_breached",
            value=sla_breached_approvals,
            target=1,
            status=_metric_status(sla_breached_approvals, target=1, reverse=True),
        ),
        OrgReadinessMetric(
            name="unread_high_alerts",
            value=unread_high_alerts,
            target=1,
            status=_metric_status(unread_high_alerts, target=1, reverse=True),
        ),
    ]

    return OrgReadinessReport(
        org_id=org.id,
        org_name=org.name,
        score=score,
        status=status,
        blockers=blockers,
        recommendations=recommendations,
        metrics=metrics,
        generated_at=now,
    )
