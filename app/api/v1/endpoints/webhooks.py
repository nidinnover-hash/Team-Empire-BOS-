from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.webhook import (
    WebhookDeliveryListResponse,
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointCreateResponse,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
    WebhookTestResponse,
)
from app.services import webhook as webhook_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


@router.post("", response_model=WebhookEndpointCreateResponse, status_code=201)
async def create_webhook(
    data: WebhookEndpointCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookEndpointCreateResponse:
    try:
        endpoint, signing_secret = await webhook_service.create_webhook_endpoint(
            db,
            organization_id=int(actor["org_id"]),
            url=data.url,
            description=data.description,
            event_types=data.event_types,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_action(
        db,
        event_type="webhook_endpoint_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        payload_json={"url": endpoint.url, "event_types": endpoint.event_types},
    )
    return WebhookEndpointCreateResponse(
        id=endpoint.id,
        url=endpoint.url,
        description=endpoint.description,
        event_types=endpoint.event_types or [],
        is_active=endpoint.is_active,
        signing_secret=signing_secret,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )


@router.get("", response_model=list[WebhookEndpointRead])
async def list_webhooks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[WebhookEndpointRead]:
    endpoints = await webhook_service.list_webhook_endpoints(
        db, int(actor["org_id"]), limit=limit, offset=offset
    )
    return [WebhookEndpointRead.model_validate(e) for e in endpoints]


@router.get("/{endpoint_id}", response_model=WebhookEndpointRead)
async def get_webhook(
    endpoint_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookEndpointRead:
    endpoint = await webhook_service.get_webhook_endpoint(
        db, endpoint_id, int(actor["org_id"])
    )
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    return WebhookEndpointRead.model_validate(endpoint)


@router.patch("/{endpoint_id}", response_model=WebhookEndpointRead)
async def update_webhook(
    endpoint_id: int,
    data: WebhookEndpointUpdate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookEndpointRead:
    kwargs: dict = {}
    if data.url is not None:
        kwargs["url"] = data.url
    if data.description is not None:
        kwargs["description"] = data.description
    if data.event_types is not None:
        kwargs["event_types"] = data.event_types
    if data.is_active is not None:
        kwargs["is_active"] = data.is_active
    try:
        endpoint = await webhook_service.update_webhook_endpoint(
            db, endpoint_id, int(actor["org_id"]), **kwargs
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    await record_action(
        db,
        event_type="webhook_endpoint_updated",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        payload_json={"url": endpoint.url},
    )
    return WebhookEndpointRead.model_validate(endpoint)


@router.delete("/{endpoint_id}", status_code=204)
async def delete_webhook(
    endpoint_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    deleted = await webhook_service.delete_webhook_endpoint(
        db, endpoint_id, int(actor["org_id"])
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    await record_action(
        db,
        event_type="webhook_endpoint_deleted",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="webhook_endpoint",
        entity_id=endpoint_id,
        payload_json={},
    )


@router.post("/{endpoint_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    endpoint_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookTestResponse:
    result = await webhook_service.send_test_webhook(
        db, endpoint_id, int(actor["org_id"])
    )
    if result.get("error") == "Webhook endpoint not found":
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    return WebhookTestResponse(**result)


@router.get(
    "/{endpoint_id}/deliveries", response_model=WebhookDeliveryListResponse
)
async def get_deliveries(
    endpoint_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookDeliveryListResponse:
    endpoint = await webhook_service.get_webhook_endpoint(
        db, endpoint_id, int(actor["org_id"])
    )
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    deliveries = await webhook_service.list_deliveries(
        db, endpoint_id, int(actor["org_id"]), limit=limit, offset=offset
    )
    return WebhookDeliveryListResponse(
        count=len(deliveries),
        items=[WebhookDeliveryRead.model_validate(d) for d in deliveries],
    )
