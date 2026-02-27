from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.social import (
    SocialPostCreate,
    SocialPostRead,
    SocialPostStatus,
    SocialPostStatusUpdate,
    SocialSummaryRead,
)
from app.services import social as social_service

router = APIRouter(prefix="/social", tags=["Social"])


def _allowed_content_mode_for_actor(actor: dict) -> str:
    purpose = str(actor.get("purpose") or "professional").strip().lower()
    return "entertainment" if purpose == "entertainment" else "social_media"


@router.post("/posts", response_model=SocialPostRead, status_code=201)
async def create_social_post(
    data: SocialPostCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SocialPostRead:
    allowed_mode = _allowed_content_mode_for_actor(actor)
    if data.content_mode != allowed_mode:
        raise HTTPException(
            status_code=403,
            detail=f"This login is restricted to '{allowed_mode}' mode",
        )
    post = await social_service.create_social_post(
        db=db,
        data=data,
        organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]),
    )
    await record_action(
        db=db,
        organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]),
        event_type="social_post_created",
        entity_type="social_post",
        entity_id=post.id,
        payload_json={"status": post.status, "platform": post.platform},
    )
    return post


@router.get("/posts", response_model=list[SocialPostRead])
async def list_social_posts(
    status: SocialPostStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> list[SocialPostRead]:
    allowed_mode = _allowed_content_mode_for_actor(actor)
    rows = await social_service.list_social_posts(
        db=db,
        organization_id=int(actor["org_id"]),
        limit=limit,
        status=status,
        content_mode=allowed_mode,
    )
    return rows


@router.patch("/posts/{post_id}/status", response_model=SocialPostRead)
async def update_social_post_status(
    post_id: int,
    data: SocialPostStatusUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SocialPostRead:
    allowed_mode = _allowed_content_mode_for_actor(actor)
    existing = await social_service.get_social_post(
        db=db,
        organization_id=int(actor["org_id"]),
        post_id=post_id,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Social post not found")
    if existing.content_mode != allowed_mode:
        raise HTTPException(status_code=403, detail=f"This login is restricted to '{allowed_mode}' mode")
    try:
        post = await social_service.update_social_post_status(
            db=db,
            post_id=post_id,
            data=data,
            organization_id=int(actor["org_id"]),
            actor_user_id=int(actor["id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Invalid operation on social post") from exc
    if post is None:
        raise HTTPException(status_code=404, detail="Social post not found")
    await record_action(
        db=db,
        organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]),
        event_type="social_post_status_updated",
        entity_type="social_post",
        entity_id=post.id,
        payload_json={"status": post.status, "platform": post.platform},
    )
    return post


@router.get("/summary", response_model=SocialSummaryRead)
async def social_summary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> SocialSummaryRead:
    allowed_mode = _allowed_content_mode_for_actor(actor)
    payload = await social_service.get_social_summary(
        db=db,
        organization_id=int(actor["org_id"]),
        content_mode=allowed_mode,
    )
    return SocialSummaryRead(**payload)


@router.post("/posts/{post_id}/approve", response_model=SocialPostRead)
async def approve_social_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SocialPostRead:
    allowed_mode = _allowed_content_mode_for_actor(actor)
    existing = await social_service.get_social_post(
        db=db,
        organization_id=int(actor["org_id"]),
        post_id=post_id,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Social post not found")
    if existing.content_mode != allowed_mode:
        raise HTTPException(status_code=403, detail=f"This login is restricted to '{allowed_mode}' mode")
    post = await social_service.approve_social_post(
        db=db,
        post_id=post_id,
        organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]),
    )
    if post is None:
        raise HTTPException(status_code=404, detail="Social post not found")
    await record_action(
        db=db,
        organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]),
        event_type="social_post_approved",
        entity_type="social_post",
        entity_id=post.id,
        payload_json={"status": post.status, "platform": post.platform},
    )
    return post


@router.post("/posts/{post_id}/publish", response_model=SocialPostRead)
async def publish_social_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SocialPostRead:
    allowed_mode = _allowed_content_mode_for_actor(actor)
    existing = await social_service.get_social_post(
        db=db,
        organization_id=int(actor["org_id"]),
        post_id=post_id,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="Social post not found")
    if existing.content_mode != allowed_mode:
        raise HTTPException(status_code=403, detail=f"This login is restricted to '{allowed_mode}' mode")
    try:
        post = await social_service.publish_social_post(
            db=db,
            post_id=post_id,
            organization_id=int(actor["org_id"]),
            actor_user_id=int(actor["id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Invalid operation on social post") from exc
    if post is None:
        raise HTTPException(status_code=404, detail="Social post not found")
    await record_action(
        db=db,
        organization_id=int(actor["org_id"]),
        actor_user_id=int(actor["id"]),
        event_type="social_post_published",
        entity_type="social_post",
        entity_id=post.id,
        payload_json={"status": post.status, "platform": post.platform},
    )
    return post
