"""Internal comments — threaded comments on any entity."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import internal_comment as comment_service

router = APIRouter(prefix="/internal-comments", tags=["Internal Comments"])


class CommentCreate(BaseModel):
    entity_type: str = Field(..., max_length=30)
    entity_id: int
    body: str
    parent_id: int | None = None


@router.get("")
async def list_comments(
    entity_type: str = Query(...),
    entity_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[dict]:
    return await comment_service.list_comments(
        db, organization_id=actor["org_id"], entity_type=entity_type, entity_id=entity_id,
    )


@router.post("")
async def create_comment(
    data: CommentCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> dict:
    comment = await comment_service.create_comment(
        db, organization_id=actor["org_id"], entity_type=data.entity_type,
        entity_id=data.entity_id, author_user_id=int(actor["id"]),
        body=data.body, parent_id=data.parent_id,
    )
    return {"id": comment.id, "body": comment.body, "entity_type": comment.entity_type, "entity_id": comment.entity_id}


@router.delete("/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> None:
    deleted = await comment_service.delete_comment(
        db, comment_id=comment_id, organization_id=actor["org_id"], user_id=int(actor["id"]),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
