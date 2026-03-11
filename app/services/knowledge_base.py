"""Knowledge base service."""
from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KBArticle


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


async def create_article(
    db: AsyncSession, *, organization_id: int, title: str,
    content: str, category: str | None = None,
    tags: list[str] | None = None, is_published: bool = False,
    created_by_user_id: int | None = None,
) -> KBArticle:
    row = KBArticle(
        organization_id=organization_id, title=title,
        slug=_slugify(title), content=content, category=category,
        tags_json=json.dumps(tags or []), is_published=is_published,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_articles(
    db: AsyncSession, organization_id: int, *,
    category: str | None = None, is_published: bool | None = None,
) -> list[KBArticle]:
    q = select(KBArticle).where(KBArticle.organization_id == organization_id)
    if category:
        q = q.where(KBArticle.category == category)
    if is_published is not None:
        q = q.where(KBArticle.is_published == is_published)
    q = q.order_by(KBArticle.updated_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_article(db: AsyncSession, article_id: int, organization_id: int) -> KBArticle | None:
    q = select(KBArticle).where(KBArticle.id == article_id, KBArticle.organization_id == organization_id)
    return (await db.execute(q)).scalar_one_or_none()


async def update_article(db: AsyncSession, article_id: int, organization_id: int, **kwargs) -> KBArticle | None:
    row = await get_article(db, article_id, organization_id)
    if not row:
        return None
    if "tags" in kwargs:
        kwargs["tags_json"] = json.dumps(kwargs.pop("tags") or [])
    if kwargs.get("title"):
        kwargs["slug"] = _slugify(kwargs["title"])
    for k, v in kwargs.items():
        if v is not None:
            setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return row


async def delete_article(db: AsyncSession, article_id: int, organization_id: int) -> bool:
    row = await get_article(db, article_id, organization_id)
    if not row:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def record_view(db: AsyncSession, article_id: int, organization_id: int) -> KBArticle | None:
    row = await get_article(db, article_id, organization_id)
    if not row:
        return None
    row.view_count += 1
    await db.commit()
    await db.refresh(row)
    return row


async def record_helpful(db: AsyncSession, article_id: int, organization_id: int) -> KBArticle | None:
    row = await get_article(db, article_id, organization_id)
    if not row:
        return None
    row.helpful_count += 1
    await db.commit()
    await db.refresh(row)
    return row


async def search_articles(db: AsyncSession, organization_id: int, query: str) -> list[KBArticle]:
    q = (
        select(KBArticle)
        .where(
            KBArticle.organization_id == organization_id,
            KBArticle.is_published == True,  # noqa: E712
            KBArticle.title.ilike(f"%{query}%") | KBArticle.content.ilike(f"%{query}%"),
        )
        .order_by(KBArticle.view_count.desc())
        .limit(20)
    )
    return list((await db.execute(q)).scalars().all())
