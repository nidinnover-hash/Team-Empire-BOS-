from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def send_pending_alert(
    db: AsyncSession,
    *,
    org_id: int,
    entity_type: str,
    entity_id: int,
    title: str,
    detail: str,
) -> None:
    _ = (db, org_id, entity_type, entity_id, title, detail)
