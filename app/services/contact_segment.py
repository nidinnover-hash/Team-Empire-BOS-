"""Contact segment service — saved filters with dynamic evaluation."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.contact_segment import ContactSegment


async def create_segment(
    db: AsyncSession, organization_id: int, created_by_user_id: int | None = None, **kwargs,
) -> ContactSegment:
    if "filters" in kwargs:
        kwargs["filters_json"] = json.dumps(kwargs.pop("filters"))
    segment = ContactSegment(
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        **kwargs,
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)
    return segment


async def list_segments(
    db: AsyncSession, organization_id: int,
) -> list[ContactSegment]:
    result = await db.execute(
        select(ContactSegment).where(
            ContactSegment.organization_id == organization_id,
            ContactSegment.is_active.is_(True),
        ).order_by(ContactSegment.id)
    )
    return list(result.scalars().all())


async def get_segment(
    db: AsyncSession, segment_id: int, organization_id: int,
) -> ContactSegment | None:
    result = await db.execute(
        select(ContactSegment).where(
            ContactSegment.id == segment_id,
            ContactSegment.organization_id == organization_id,
        )
    )
    return result.scalar_one_or_none()


async def update_segment(
    db: AsyncSession, segment_id: int, organization_id: int, **kwargs,
) -> ContactSegment | None:
    segment = await get_segment(db, segment_id, organization_id)
    if segment is None:
        return None
    if "filters" in kwargs:
        kwargs["filters_json"] = json.dumps(kwargs.pop("filters"))
    for k, v in kwargs.items():
        if v is not None and hasattr(segment, k):
            setattr(segment, k, v)
    await db.commit()
    await db.refresh(segment)
    return segment


async def delete_segment(
    db: AsyncSession, segment_id: int, organization_id: int,
) -> bool:
    segment = await get_segment(db, segment_id, organization_id)
    if segment is None:
        return False
    segment.is_active = False
    await db.commit()
    return True


async def evaluate_segment(
    db: AsyncSession, segment_id: int, organization_id: int, limit: int = 100,
) -> dict:
    """Evaluate a segment's filters and return matching contacts."""
    segment = await get_segment(db, segment_id, organization_id)
    if segment is None:
        return {"error": "Segment not found"}

    filters = json.loads(segment.filters_json) if segment.filters_json else {}

    q = select(Contact).where(Contact.organization_id == organization_id)

    if "pipeline_stage" in filters:
        q = q.where(Contact.pipeline_stage == filters["pipeline_stage"])
    if "lead_score_min" in filters:
        q = q.where(Contact.lead_score >= int(filters["lead_score_min"]))
    if "lead_score_max" in filters:
        q = q.where(Contact.lead_score <= int(filters["lead_score_max"]))
    if "relationship" in filters:
        q = q.where(Contact.relationship == filters["relationship"])
    if "lead_source" in filters:
        q = q.where(Contact.lead_source == filters["lead_source"])
    if "tags_contain" in filters:
        q = q.where(Contact.tags.contains(filters["tags_contain"]))
    if "company_contains" in filters:
        q = q.where(Contact.company.contains(filters["company_contains"]))

    q = q.limit(limit).order_by(Contact.id.desc())
    result = await db.execute(q)
    contacts = list(result.scalars().all())

    return {
        "segment_id": segment.id,
        "segment_name": segment.name,
        "filters": filters,
        "match_count": len(contacts),
        "contacts": [
            {"id": c.id, "name": c.name, "email": c.email, "pipeline_stage": c.pipeline_stage, "lead_score": c.lead_score}
            for c in contacts
        ],
    }
