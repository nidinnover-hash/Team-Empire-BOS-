"""API key management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
)
from app.services import api_key as api_key_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.middleware import check_per_route_rate_limit, get_client_ip

    if not check_per_route_rate_limit(get_client_ip(request), "api_key_create", max_requests=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many API key requests. Try again later.")
    try:
        api_key, full_key = await api_key_service.create_api_key(
            db,
            organization_id=int(user["org_id"]),
            user_id=int(user["id"]),
            name=body.name,
            scopes=body.scopes,
            expires_in_days=body.expires_in_days,
        )
    except ValueError as exc:
        logger.warning("API key creation rejected: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid API key parameters") from exc
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
    request: Request,
    user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
) -> None:
    from app.core.middleware import check_per_route_rate_limit, get_client_ip

    if not check_per_route_rate_limit(get_client_ip(request), "api_key_revoke", max_requests=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many API key requests. Try again later.")
    ok = await api_key_service.revoke_api_key(
        db,
        key_id=key_id,
        organization_id=int(user["org_id"]),
        user_id=int(user["id"]),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
