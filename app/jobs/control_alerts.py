"""
Control alerts job — notifies when pending approvals exceed threshold,
study-abroad at risk > 0, or high-value money approvals need attention.
Runs on scheduler cycle; dedupes to at most one notification per alert type per org per day.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval
from app.models.study_abroad import StudyAbroadApplication, StudyAbroadApplicationStep

logger = logging.getLogger(__name__)

# At most one notification per (org, alert_key) per day
_last_control_alert_key_by_org: dict[tuple[int, str], str] = {}

PENDING_APPROVALS_THRESHOLD = 5


async def run_control_alerts(db: AsyncSession, org_id: int) -> None:
    """
    Emit in-app notifications (and optional Slack) when:
    - Pending approvals >= PENDING_APPROVALS_THRESHOLD
    - Study abroad at-risk count > 0
    Dedup: one per alert type per org per calendar day.
    """
    from app.services.notification import create_notification

    now = datetime.now(UTC)
    day_key = now.strftime("%Y-%m-%d")

    # Pending approvals count
    pending_result = await db.execute(
        select(func.count(Approval.id)).where(
            Approval.organization_id == org_id,
            Approval.status == "pending",
        )
    )
    pending_count = int(pending_result.scalar() or 0)

    if pending_count >= PENDING_APPROVALS_THRESHOLD:
        alert_key = "pending_approvals_high"
        if _last_control_alert_key_by_org.get((org_id, alert_key)) != day_key:
            try:
                await create_notification(
                    db,
                    organization_id=org_id,
                    type="control_alert",
                    severity="warning",
                    title="Control: Many pending approvals",
                    message=f"{pending_count} approvals are pending. Review in Control Dashboard or Agent Chat.",
                    source="control_alerts",
                    entity_type="control",
                    entity_id=None,
                )
                await db.commit()
                _last_control_alert_key_by_org[(org_id, alert_key)] = day_key
            except Exception as exc:
                logger.debug("Control alert notification failed: %s", type(exc).__name__)

    # Study abroad at-risk
    at_risk_result = await db.execute(
        select(func.count(StudyAbroadApplicationStep.id))
        .select_from(StudyAbroadApplicationStep)
        .join(StudyAbroadApplication, StudyAbroadApplication.id == StudyAbroadApplicationStep.application_id)
        .where(
            StudyAbroadApplication.organization_id == org_id,
            StudyAbroadApplicationStep.deadline.isnot(None),
            StudyAbroadApplicationStep.deadline < now,
            StudyAbroadApplicationStep.completed_at.is_(None),
        )
    )
    at_risk_count = int(at_risk_result.scalar() or 0)

    if at_risk_count > 0:
        alert_key = "study_abroad_at_risk"
        if _last_control_alert_key_by_org.get((org_id, alert_key)) != day_key:
            try:
                await create_notification(
                    db,
                    organization_id=org_id,
                    type="control_alert",
                    severity="warning",
                    title="Control: Study abroad steps at risk",
                    message=f"{at_risk_count} application step(s) are past deadline and not completed. Check Control Dashboard.",
                    source="control_alerts",
                    entity_type="control",
                    entity_id=None,
                )
                await db.commit()
                _last_control_alert_key_by_org[(org_id, alert_key)] = day_key
            except Exception as exc:
                logger.debug("Control alert notification failed: %s", type(exc).__name__)
