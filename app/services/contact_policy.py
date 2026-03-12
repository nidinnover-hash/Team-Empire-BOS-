"""Contact policy — can_send (who we contact, how often, with what). BOS is the control plane."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_send_policy import ContactSendLog, ContactSendPolicy

DEFAULT_MAX_PER_CONTACT_PER_DAY = 5


async def can_send(
    db: AsyncSession,
    organization_id: int,
    *,
    contact_id: str,
    channel: str,
    campaign_id: str | None = None,
) -> dict:
    """
    Decide whether a send is allowed using org policy and send log.
    Returns: allowed, reason, recommended_time_utc.
    """
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Policy for this org+channel
    policy_result = await db.execute(
        select(ContactSendPolicy)
        .where(
            ContactSendPolicy.organization_id == organization_id,
            ContactSendPolicy.channel == channel,
        )
        .limit(1)
    )
    policy = policy_result.scalar_one_or_none()
    max_per_day = policy.max_per_contact_per_day if policy else DEFAULT_MAX_PER_CONTACT_PER_DAY

    # Count sends today for this contact+channel
    count_result = await db.execute(
        select(func.count(ContactSendLog.id))
        .where(
            ContactSendLog.organization_id == organization_id,
            ContactSendLog.contact_id == contact_id,
            ContactSendLog.channel == channel,
            ContactSendLog.sent_at >= today_start,
        )
    )
    count = count_result.scalar() or 0

    if count >= max_per_day:
        return {
            "allowed": False,
            "reason": f"Max {max_per_day} sends per contact per day for channel {channel} already reached.",
            "recommended_time_utc": (today_start + timedelta(days=1)).isoformat(),
        }
    return {
        "allowed": True,
        "reason": None,
        "recommended_time_utc": now.isoformat(),
    }


async def record_send(
    db: AsyncSession,
    organization_id: int,
    *,
    contact_id: str,
    channel: str,
) -> None:
    """Call after a send is made so can_send counts it. Other systems should call this."""
    row = ContactSendLog(
        organization_id=organization_id,
        contact_id=contact_id,
        channel=channel,
        sent_at=datetime.now(UTC),
    )
    db.add(row)
    await db.commit()
