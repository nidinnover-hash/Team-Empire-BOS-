from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.webhook import (
    WebhookDeliveryListResponse,
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointCreateResponse,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
    WebhookReplayResponse,
    WebhookTestResponse,
)
from app.services import webhook as webhook_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = logging.getLogger(__name__)


def _enrich_delivery(d: object) -> WebhookDeliveryRead:
    """Validate delivery and attach error classification for failed/dead-letter entries."""
    read = WebhookDeliveryRead.model_validate(d)
    if getattr(d, "status", "") in {"failed", "dead_letter"}:
        return read.model_copy(
            update={
                "error_category": webhook_service.classify_delivery_error(
                    getattr(d, "error_message", None),
                    getattr(d, "response_status_code", None),
                )
            }
        )
    return read


@router.post("", response_model=WebhookEndpointCreateResponse, status_code=201)
async def create_webhook(
    data: WebhookEndpointCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookEndpointCreateResponse:
    scope = f"webhook_create:{int(actor['org_id'])}"
    fingerprint = build_fingerprint(data.model_dump())
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return WebhookEndpointCreateResponse.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
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
        event_type="security_webhook_endpoint_created",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        payload_json={"url": endpoint.url, "event_types": endpoint.event_types},
    )
    response = WebhookEndpointCreateResponse(
        id=endpoint.id,
        url=endpoint.url,
        description=endpoint.description,
        event_types=endpoint.event_types or [],
        is_active=endpoint.is_active,
        signing_secret=signing_secret,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookEndpointRead:
    scope = f"webhook_update:{int(actor['org_id'])}:{endpoint_id}"
    fingerprint = build_fingerprint(data.model_dump(exclude_unset=True))
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return WebhookEndpointRead.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
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
        event_type="security_webhook_endpoint_updated",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        payload_json={"url": endpoint.url},
    )
    response = WebhookEndpointRead.model_validate(endpoint)
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


@router.delete("/{endpoint_id}", status_code=204)
async def delete_webhook(
    endpoint_id: int,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> None:
    scope = f"webhook_delete:{int(actor['org_id'])}:{endpoint_id}"
    fingerprint = build_fingerprint({"endpoint_id": endpoint_id})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict") from exc
    deleted = await webhook_service.delete_webhook_endpoint(
        db, endpoint_id, int(actor["org_id"])
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    await record_action(
        db,
        event_type="security_webhook_endpoint_deleted",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="webhook_endpoint",
        entity_id=endpoint_id,
        payload_json={},
    )
    if idempotency_key:
        store_response(scope, idempotency_key, {"ok": True}, fingerprint=fingerprint)


@router.post("/{endpoint_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    request: Request,
    endpoint_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookTestResponse:
    from app.core.middleware import check_per_route_rate_limit, get_client_ip
    if not check_per_route_rate_limit(get_client_ip(request), "webhook_test", max_requests=5, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many test requests. Try again later.")
    result = await webhook_service.send_test_webhook(
        db, endpoint_id, int(actor["org_id"])
    )
    if result.get("error") == "Webhook endpoint not found":
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    return WebhookTestResponse(**result)


@router.get("/deliveries/all", response_model=WebhookDeliveryListResponse)
async def get_all_deliveries(
    event: str | None = Query(None, max_length=100),
    status: str | None = Query(None, max_length=20),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookDeliveryListResponse:
    """Global webhook delivery history across all endpoints."""
    deliveries = await webhook_service.list_all_deliveries(
        db, int(actor["org_id"]), event=event, status=status, limit=limit, offset=offset
    )
    return WebhookDeliveryListResponse(
        count=len(deliveries),
        items=[_enrich_delivery(d) for d in deliveries],
    )


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
        items=[_enrich_delivery(d) for d in deliveries],
    )


@router.get("/deliveries/dead-letter", response_model=WebhookDeliveryListResponse)
async def get_dead_letter_deliveries(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10_000),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookDeliveryListResponse:
    deliveries = await webhook_service.list_dead_letter_deliveries(
        db, int(actor["org_id"]), limit=limit, offset=offset
    )
    return WebhookDeliveryListResponse(
        count=len(deliveries),
        items=[_enrich_delivery(d) for d in deliveries],
    )


@router.post("/deliveries/{delivery_id}/replay", response_model=WebhookReplayResponse)
async def replay_dead_letter_delivery(
    delivery_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WebhookReplayResponse:
    replayed = await webhook_service.replay_dead_letter_delivery(
        db,
        organization_id=int(actor["org_id"]),
        delivery_id=delivery_id,
    )
    if replayed is None:
        raise HTTPException(status_code=404, detail="Dead-letter delivery not found")
    await record_action(
        db,
        event_type="security_webhook_dead_letter_replayed",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="webhook_delivery",
        entity_id=delivery_id,
        payload_json={"replayed_delivery_id": replayed.id},
    )
    return WebhookReplayResponse(ok=True, replayed_delivery_id=replayed.id)
