from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import SocialPost
from app.schemas.social import SocialPostCreate, SocialPostStatusUpdate

_ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"draft", "queued", "approved", "failed"},
    "queued": {"queued", "approved", "failed"},
    "approved": {"approved", "queued", "published", "failed"},
    "published": {"published"},
    "failed": {"failed", "draft", "queued"},
}


def _validate_status_transition(current_status: str, next_status: str) -> None:
    allowed = _ALLOWED_STATUS_TRANSITIONS.get(current_status, {current_status})
    if next_status not in allowed:
        raise ValueError(f"Invalid status transition: {current_status} -> {next_status}")


async def create_social_post(
    db: AsyncSession,
    data: SocialPostCreate,
    organization_id: int,
    actor_user_id: int | None,
) -> SocialPost:
    post = SocialPost(
        organization_id=organization_id,
        content_mode=data.content_mode,
        platform=data.platform,
        title=data.title,
        content=data.content,
        scheduled_for=data.scheduled_for,
        media_url=data.media_url,
        created_by_user_id=actor_user_id,
        status="queued" if data.scheduled_for else "draft",
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


async def get_social_post(
    db: AsyncSession,
    organization_id: int,
    post_id: int,
) -> SocialPost | None:
    result = await db.execute(
        select(SocialPost).where(
            SocialPost.organization_id == organization_id,
            SocialPost.id == post_id,
        )
    )
    return cast(SocialPost | None, result.scalar_one_or_none())


async def list_social_posts(
    db: AsyncSession,
    organization_id: int,
    limit: int = 50,
    status: str | None = None,
    content_mode: str | None = None,
) -> list[SocialPost]:
    q = select(SocialPost).where(SocialPost.organization_id == organization_id)
    if status:
        q = q.where(SocialPost.status == status)
    if content_mode:
        q = q.where(SocialPost.content_mode == content_mode)
    result = await db.execute(q.order_by(SocialPost.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def update_social_post_status(
    db: AsyncSession,
    post_id: int,
    data: SocialPostStatusUpdate,
    organization_id: int,
    actor_user_id: int | None,
) -> SocialPost | None:
    result = await db.execute(
        select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.organization_id == organization_id,
        )
    )
    post = cast(SocialPost | None, result.scalar_one_or_none())
    if post is None:
        return None

    _validate_status_transition(str(post.status), str(data.status))
    post.status = data.status
    if data.status == "approved":
        post.approved_by_user_id = actor_user_id
    if data.status == "published":
        post.published_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(post)
    return post


async def get_social_summary(
    db: AsyncSession,
    organization_id: int,
    content_mode: str | None = None,
) -> dict[str, int]:
    query = select(SocialPost.status, func.count()).where(SocialPost.organization_id == organization_id)
    if content_mode:
        query = query.where(SocialPost.content_mode == content_mode)
    result = await db.execute(query.group_by(SocialPost.status))
    counts = {str(status): int(count) for status, count in result.all()}
    return {
        "total_posts": sum(counts.values()),
        "draft": counts.get("draft", 0),
        "queued": counts.get("queued", 0),
        "approved": counts.get("approved", 0),
        "published": counts.get("published", 0),
        "failed": counts.get("failed", 0),
    }


async def approve_social_post(
    db: AsyncSession,
    post_id: int,
    organization_id: int,
    actor_user_id: int | None,
) -> SocialPost | None:
    return await update_social_post_status(
        db=db,
        post_id=post_id,
        data=SocialPostStatusUpdate(status="approved"),
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )


async def publish_social_post(
    db: AsyncSession,
    post_id: int,
    organization_id: int,
    actor_user_id: int | None,
) -> SocialPost | None:
    result = await db.execute(
        select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.organization_id == organization_id,
        )
    )
    post = cast(SocialPost | None, result.scalar_one_or_none())
    if post is None:
        return None
    if post.status not in ("approved", "queued"):
        raise ValueError("Post must be approved or queued before publishing")
    post.status = "published"
    post.published_at = datetime.now(timezone.utc)
    if post.approved_by_user_id is None:
        post.approved_by_user_id = actor_user_id
    await db.commit()
    await db.refresh(post)
    return post


async def publish_due_queued_posts(db: AsyncSession, organization_id: int) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(SocialPost).where(
            SocialPost.organization_id == organization_id,
            SocialPost.status == "queued",
            SocialPost.scheduled_for.is_not(None),
            SocialPost.scheduled_for <= now,
            SocialPost.approved_by_user_id.is_not(None),
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return 0
    for post in rows:
        post.status = "published"
        post.published_at = now
    await db.commit()
    return len(rows)
