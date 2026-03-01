"""API key management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
)
from app.services import api_key as api_key_service

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    api_key, full_key = await api_key_service.create_api_key(
        db,
        organization_id=int(user["org_id"]),
        user_id=int(user["id"]),
        name=body.name,
        scopes=body.scopes,
        expires_in_days=body.expires_in_days,
    )
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": full_key,
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at,
        "created_at": api_key.created_at,
    }


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    keys = await api_key_service.list_api_keys(
        db,
        organization_id=int(user["org_id"]),
        user_id=int(user["id"]),
    )
    return {
        "count": len(keys),
        "items": keys,
    }


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: int,
    user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> None:
    ok = await api_key_service.revoke_api_key(
        db,
        key_id=key_id,
        organization_id=int(user["org_id"]),
        user_id=int(user["id"]),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
