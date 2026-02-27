from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


async def trigger_org_webhooks(
    db: AsyncSession,
    *,
    organization_id: int,
    event: str,
    payload: dict[str, Any],
) -> None:
    _ = (db, organization_id, event, payload)
