"""Contact policy — can_send (who we contact, how often, with what). BOS is the control plane."""

from __future__ import annotations

from datetime import UTC, datetime

# Default: allow; recommended time is now. Extend with rate limits and suppression later.


async def can_send(
    organization_id: int,
    *,
    contact_id: str,
    channel: str,
    campaign_id: str | None = None,
) -> dict:
    """
    Decide whether a send is allowed. Other systems must call this before sending.
    Returns: allowed, reason, recommended_time_utc.
    """
    now = datetime.now(UTC)
    return {
        "allowed": True,
        "reason": None,
        "recommended_time_utc": now.isoformat(),
    }
