"""Internal comment service — threaded comments on entities."""
from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.internal_comment import InternalComment
from app.models.user import User


def _extract_mentions(body: str) -> list[int]:
    """Extract @user_id mentions from comment body."""
    return [int(m) for m in re.findall(r"@(\d+)", body)]


async def create_comment(
    db: AsyncSession, organization_id: int, entity_type: str, entity_id: int,
    author_user_id: int, body: str, parent_id: int | None = None,
) -> InternalComment:
    mentions = _extract_mentions(body)
    comment = InternalComment(
        organization_id=organization_id, entity_type=entity_type, entity_id=entity_id,
        author_user_id=author_user_id, body=body, parent_id=parent_id,
        mentions_json=json.dumps(mentions) if mentions else None,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def list_comments(
    db: AsyncSession, organization_id: int, entity_type: str, entity_id: int,
) -> list[dict]:
    result = await db.execute(
        select(InternalComment, User.name, User.email)
        .join(User, User.id == InternalComment.author_user_id)
        .where(
            InternalComment.organization_id == organization_id,
            InternalComment.entity_type == entity_type,
            InternalComment.entity_id == entity_id,
        )
        .order_by(InternalComment.created_at)
    )
    return [
        {
            "id": c.id, "body": c.body, "parent_id": c.parent_id,
            "author_user_id": c.author_user_id, "author_name": name, "author_email": email,
            "mentions": json.loads(c.mentions_json) if c.mentions_json else [],
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c, name, email in result.all()
    ]


async def delete_comment(
    db: AsyncSession, comment_id: int, organization_id: int, user_id: int,
) -> bool:
    result = await db.execute(
        select(InternalComment).where(
            InternalComment.id == comment_id,
            InternalComment.organization_id == organization_id,
            InternalComment.author_user_id == user_id,
        )
    )
    comment = result.scalar_one_or_none()
    if not comment:
        return False
    await db.delete(comment)
    await db.commit()
    return True
