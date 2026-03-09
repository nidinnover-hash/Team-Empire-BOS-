"""Tag management service — CRUD, merge, and usage tracking."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag


async def create_tag(db: AsyncSession, organization_id: int, name: str, color: str = "#6366f1") -> Tag:
    tag = Tag(organization_id=organization_id, name=name.strip().lower(), color=color)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


async def list_tags(db: AsyncSession, organization_id: int, search: str | None = None) -> list[Tag]:
    q = select(Tag).where(Tag.organization_id == organization_id)
    if search:
        q = q.where(Tag.name.contains(search.lower()))
    result = await db.execute(q.order_by(Tag.usage_count.desc(), Tag.name))
    return list(result.scalars().all())


async def update_tag(db: AsyncSession, tag_id: int, organization_id: int, **kwargs) -> Tag | None:
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, Tag.organization_id == organization_id)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        return None
    for k, v in kwargs.items():
        if v is not None and hasattr(tag, k):
            setattr(tag, k, v if k != "name" else v.strip().lower())
    await db.commit()
    await db.refresh(tag)
    return tag


async def delete_tag(db: AsyncSession, tag_id: int, organization_id: int) -> bool:
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, Tag.organization_id == organization_id)
    )
    tag = result.scalar_one_or_none()
    if not tag:
        return False
    await db.delete(tag)
    await db.commit()
    return True


async def merge_tags(
    db: AsyncSession, organization_id: int, source_tag_id: int, target_tag_id: int,
) -> Tag | None:
    """Merge source tag into target tag (adds usage counts, deletes source)."""
    src_res = await db.execute(
        select(Tag).where(Tag.id == source_tag_id, Tag.organization_id == organization_id)
    )
    source = src_res.scalar_one_or_none()
    tgt_res = await db.execute(
        select(Tag).where(Tag.id == target_tag_id, Tag.organization_id == organization_id)
    )
    target = tgt_res.scalar_one_or_none()
    if not source or not target:
        return None
    target.usage_count += source.usage_count
    await db.delete(source)
    await db.commit()
    await db.refresh(target)
    return target


async def increment_usage(db: AsyncSession, tag_id: int) -> None:
    result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = result.scalar_one_or_none()
    if tag:
        tag.usage_count += 1
        await db.commit()
