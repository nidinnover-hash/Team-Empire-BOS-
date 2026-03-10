"""Knowledge base endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.services import knowledge_base as svc

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


class KBArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    organization_id: int
    title: str
    slug: str
    content: str
    category: str | None = None
    is_published: bool
    view_count: int
    helpful_count: int
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class KBArticleCreate(BaseModel):
    title: str
    content: str
    category: str | None = None
    tags: list[str] | None = None
    is_published: bool = False


class KBArticleUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    is_published: bool | None = None


@router.post("", response_model=KBArticleOut, status_code=201)
async def create_article(
    body: KBArticleCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.create_article(
        db, organization_id=actor["org_id"],
        created_by_user_id=actor["id"], **body.model_dump(),
    )


@router.get("", response_model=list[KBArticleOut])
async def list_articles(
    category: str | None = None,
    is_published: bool | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    return await svc.list_articles(db, actor["org_id"], category=category, is_published=is_published)


@router.get("/search", response_model=list[KBArticleOut])
async def search_articles(
    q: str = "",
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    if not q:
        return []
    return await svc.search_articles(db, actor["org_id"], q)


@router.get("/{article_id}", response_model=KBArticleOut)
async def get_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.get_article(db, article_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Article not found")
    return row


@router.put("/{article_id}", response_model=KBArticleOut)
async def update_article(
    article_id: int,
    body: KBArticleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.update_article(db, article_id, actor["org_id"], **body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Article not found")
    return row


@router.delete("/{article_id}", status_code=204)
async def delete_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
):
    ok = await svc.delete_article(db, article_id, actor["org_id"])
    if not ok:
        raise HTTPException(404, "Article not found")


@router.post("/{article_id}/view", response_model=KBArticleOut)
async def record_view(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.record_view(db, article_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Article not found")
    return row


@router.post("/{article_id}/helpful", response_model=KBArticleOut)
async def record_helpful(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
):
    row = await svc.record_helpful(db, article_id, actor["org_id"])
    if not row:
        raise HTTPException(404, "Article not found")
    return row
