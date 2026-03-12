"""Contact scoring history service."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_score_history import ContactScoreSnapshot


async def record_score(
    db: AsyncSession, *, organization_id: int, contact_id: int,
    score: int, previous_score: int | None = None,
    change_reason: str | None = None, source: str = "manual",
    details_json: str | None = None,
) -> ContactScoreSnapshot:
    row = ContactScoreSnapshot(
        organization_id=organization_id, contact_id=contact_id,
        score=score, previous_score=previous_score,
        change_reason=change_reason, source=source,
        details_json=details_json,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_history(
    db: AsyncSession, organization_id: int, contact_id: int, *, limit: int = 50,
) -> list[ContactScoreSnapshot]:
    q = (
        select(ContactScoreSnapshot)
        .where(
            ContactScoreSnapshot.organization_id == organization_id,
            ContactScoreSnapshot.contact_id == contact_id,
        )
        .order_by(ContactScoreSnapshot.created_at.desc())
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())


async def get_latest_score(db: AsyncSession, organization_id: int, contact_id: int) -> ContactScoreSnapshot | None:
    q = (
        select(ContactScoreSnapshot)
        .where(
            ContactScoreSnapshot.organization_id == organization_id,
            ContactScoreSnapshot.contact_id == contact_id,
        )
        .order_by(ContactScoreSnapshot.created_at.desc())
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def get_trend(db: AsyncSession, organization_id: int, contact_id: int, *, limit: int = 30) -> list[dict]:
    snapshots = await get_history(db, organization_id, contact_id, limit=limit)
    return [
        {"score": s.score, "previous": s.previous_score, "reason": s.change_reason, "source": s.source, "date": s.created_at.isoformat() if s.created_at else None}
        for s in reversed(snapshots)
    ]
