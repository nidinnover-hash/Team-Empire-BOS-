"""Duplicate detection service — fuzzy matching on contacts/deals."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.duplicate_detection import DuplicateMatch


def _normalize(val: str | None) -> str:
    return (val or "").strip().lower()


def _similarity_score(a: str, b: str) -> int:
    """Simple similarity: 100 if exact, 80 if one contains the other, 0 otherwise."""
    a, b = _normalize(a), _normalize(b)
    if not a or not b:
        return 0
    if a == b:
        return 100
    if a in b or b in a:
        return 80
    return 0


async def scan_contact_duplicates(
    db: AsyncSession, organization_id: int, threshold: int = 60,
) -> list[dict]:
    """Scan all contacts for potential duplicates based on name, email, phone."""
    result = await db.execute(
        select(Contact).where(Contact.organization_id == organization_id)
        .order_by(Contact.id).limit(500)
    )
    contacts = list(result.scalars().all())
    matches = []
    seen = set()
    for i, a in enumerate(contacts):
        for b in contacts[i + 1:]:
            pair = (min(a.id, b.id), max(a.id, b.id))
            if pair in seen:
                continue
            matched_fields = []
            score = 0
            name_sim = _similarity_score(a.name, b.name)
            if name_sim >= 80:
                matched_fields.append("name")
                score += name_sim * 0.4
            email_sim = _similarity_score(getattr(a, "email", ""), getattr(b, "email", ""))
            if email_sim >= 80:
                matched_fields.append("email")
                score += email_sim * 0.4
            phone_sim = _similarity_score(getattr(a, "phone", ""), getattr(b, "phone", ""))
            if phone_sim >= 80:
                matched_fields.append("phone")
                score += phone_sim * 0.2
            total = int(score)
            if total >= threshold and matched_fields:
                seen.add(pair)
                matches.append({
                    "entity_a_id": a.id, "entity_b_id": b.id,
                    "match_score": total, "match_fields": matched_fields,
                    "entity_a_name": a.name, "entity_b_name": b.name,
                })
    return matches


async def save_duplicate_match(
    db: AsyncSession, organization_id: int, entity_type: str,
    entity_a_id: int, entity_b_id: int, match_score: int, match_fields: list[str],
) -> DuplicateMatch:
    match = DuplicateMatch(
        organization_id=organization_id, entity_type=entity_type,
        entity_a_id=entity_a_id, entity_b_id=entity_b_id,
        match_score=match_score, match_fields=json.dumps(match_fields),
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match


async def list_duplicate_matches(
    db: AsyncSession, organization_id: int, entity_type: str | None = None,
    status: str = "pending", limit: int = 50,
) -> list[DuplicateMatch]:
    q = select(DuplicateMatch).where(
        DuplicateMatch.organization_id == organization_id,
        DuplicateMatch.status == status,
    )
    if entity_type:
        q = q.where(DuplicateMatch.entity_type == entity_type)
    result = await db.execute(q.order_by(DuplicateMatch.match_score.desc()).limit(limit))
    return list(result.scalars().all())


async def resolve_duplicate(
    db: AsyncSession, match_id: int, organization_id: int,
    status: str, user_id: int,
) -> DuplicateMatch | None:
    result = await db.execute(
        select(DuplicateMatch).where(
            DuplicateMatch.id == match_id,
            DuplicateMatch.organization_id == organization_id,
        )
    )
    match = result.scalar_one_or_none()
    if not match:
        return None
    match.status = status
    match.resolved_by_user_id = user_id
    match.resolved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(match)
    return match
