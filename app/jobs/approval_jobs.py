"""
Approval lifecycle jobs — runs on every scheduler cycle to enforce SLA policy.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def auto_reject_expired_approvals(db: AsyncSession, org_id: int) -> None:
    """Auto-reject pending approvals whose expires_at has passed, and notify requesters."""
    from sqlalchemy import update as sa_update

    from app.models.approval import Approval
    from app.services.notification import create_notification

    now = datetime.now(UTC)
    try:
        # Fetch expired approvals before updating so we can notify each requester
        expired_rows = (
            await db.execute(
                select(Approval).where(
                    Approval.organization_id == org_id,
                    Approval.status == "pending",
                    Approval.expires_at.isnot(None),
                    Approval.expires_at <= now,
                )
            )
        ).scalars().all()

        if not expired_rows:
            return

        await db.execute(
            sa_update(Approval)
            .where(
                Approval.organization_id == org_id,
                Approval.status == "pending",
                Approval.expires_at.isnot(None),
                Approval.expires_at <= now,
            )
            .values(status="rejected", approved_at=now)
        )
        logger.info("Auto-rejected %d expired approvals for org=%d", len(expired_rows), org_id)

        for approval in expired_rows:
            try:
                await create_notification(
                    db,
                    organization_id=org_id,
                    type="approval_expired",
                    severity="warning",
                    title=f"Approval Expired: {approval.approval_type}",
                    message="This approval request expired without a decision and was auto-rejected.",
                    source="scheduler",
                    entity_type="approval",
                    entity_id=approval.id,
                    user_id=approval.requested_by,
                )
            except (SQLAlchemyError, Exception):
                logger.debug("Failed to notify requester for expired approval id=%d", approval.id)

        await db.commit()
    except SQLAlchemyError as exc:
        logger.debug("Approval expiry cleanup failed for org=%d: %s", org_id, exc)
