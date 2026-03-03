import logging
from datetime import UTC, datetime

import fastapi
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import (
    integrations_ai,
    integrations_calendly,
    integrations_clickup,
    integrations_digitalocean,
    integrations_elevenlabs,
    integrations_github,
    integrations_google_analytics,
    integrations_google_calendar,
    integrations_hubspot,
    integrations_linkedin,
    integrations_notion,
    integrations_perplexity,
    integrations_slack,
    integrations_stripe,
    integrations_whatsapp,
)
from app.api.v1.endpoints.integrations_shared import (
    GENERIC_CONNECT_ALLOWED_TYPES,
    GENERIC_CONNECT_BLOCKED_ROUTES,
    redact_integration,
    safe_provider_error,
)
from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    IntegrationConnectRequest,
    IntegrationRead,
    IntegrationSetupGuideRead,
    IntegrationTestResult,
    SecurityCenterTrendPointRead,
    SecurityCenterTrendRead,
)
from app.services import integration as integration_service
from app.services import trend_telemetry
from app.services.token_health import get_rotation_report, rotate_oauth_token
from app.tools.google_calendar import (
    list_events_for_day,
    refresh_access_token,
)
from app.tools.whatsapp_business import get_phone_number_details

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["Integrations"])

_GENERIC_CONNECT_ALLOWED_TYPES = GENERIC_CONNECT_ALLOWED_TYPES
_GENERIC_CONNECT_BLOCKED_ROUTES = GENERIC_CONNECT_BLOCKED_ROUTES
safe_provider_error_fn = safe_provider_error
redact_integration_fn = redact_integration

# Compatibility re-exports for tests/callers that patch these symbols directly.
_sign_google_calendar_state = integrations_google_calendar._sign_google_calendar_state
_resolve_whatsapp_context = integrations_whatsapp._resolve_whatsapp_context


# Collection endpoints (no path params)

@router.get("", response_model=list[IntegrationRead])
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[IntegrationRead]:
    items = await integration_service.list_integrations(db, organization_id=actor["org_id"])
    return [redact_integration_fn(item) for item in items]


@router.post("/connect", response_model=IntegrationRead, status_code=201)
async def connect_integration(
    data: IntegrationConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationRead:
    integration_type = str(data.type)
    if integration_type in _GENERIC_CONNECT_BLOCKED_ROUTES:
        route = _GENERIC_CONNECT_BLOCKED_ROUTES[integration_type]
        raise HTTPException(
            status_code=400,
            detail=f"Use provider-specific verification endpoint: {route}",
        )
    if integration_type not in _GENERIC_CONNECT_ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Generic connect is not allowed for integration type '{integration_type}'.",
        )
    item = await integration_service.connect_integration(
        db,
        organization_id=actor["org_id"],
        integration_type=data.type,
        config_json=data.config_json,
    )
    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"type": item.type, "status": item.status},
    )
    return redact_integration_fn(item)


@router.get("/setup-guide", response_model=IntegrationSetupGuideRead)
async def integration_setup_guide(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationSetupGuideRead:
    now = datetime.now(UTC)
    org_id = int(actor["org_id"])
    connected_by_type = {
        row.type: (row.status == "connected")
        for row in await integration_service.list_integrations(db, org_id, limit=200)
    }
    specs = [
        ("github", "GitHub", "/api/v1/integrations/github/connect", "/api/v1/integrations/github/status", "/api/v1/integrations/github/sync"),
        ("clickup", "ClickUp", "/api/v1/integrations/clickup/connect", "/api/v1/integrations/clickup/status", "/api/v1/integrations/clickup/sync"),
        ("digitalocean", "DigitalOcean", "/api/v1/integrations/digitalocean/connect", "/api/v1/integrations/digitalocean/status", "/api/v1/integrations/digitalocean/sync"),
        ("slack", "Slack", "/api/v1/integrations/slack/connect", "/api/v1/integrations/slack/status", "/api/v1/integrations/slack/sync"),
        ("perplexity", "Perplexity AI", "/api/v1/integrations/perplexity/connect", "/api/v1/integrations/perplexity/status", "/api/v1/integrations/perplexity/search"),
        ("linkedin", "LinkedIn", "/api/v1/integrations/linkedin/connect", "/api/v1/integrations/linkedin/status", "/api/v1/integrations/linkedin/publish"),
        ("notion", "Notion", "/api/v1/integrations/notion/connect", "/api/v1/integrations/notion/status", "/api/v1/integrations/notion/sync"),
        ("stripe", "Stripe", "/api/v1/integrations/stripe/connect", "/api/v1/integrations/stripe/status", "/api/v1/integrations/stripe/sync"),
        ("google_analytics", "Google Analytics", "/api/v1/integrations/google-analytics/connect", "/api/v1/integrations/google-analytics/status", "/api/v1/integrations/google-analytics/sync"),
        ("calendly", "Calendly", "/api/v1/integrations/calendly/connect", "/api/v1/integrations/calendly/status", "/api/v1/integrations/calendly/sync"),
        ("elevenlabs", "ElevenLabs", "/api/v1/integrations/elevenlabs/connect", "/api/v1/integrations/elevenlabs/status", "/api/v1/integrations/elevenlabs/tts"),
        ("hubspot", "HubSpot CRM", "/api/v1/integrations/hubspot/connect", "/api/v1/integrations/hubspot/status", "/api/v1/integrations/hubspot/sync"),
    ]
    items: list[dict[str, object]] = []
    for key, label, connect_ep, status_ep, sync_ep in specs:
        connected = bool(connected_by_type.get(key, False))
        if connected:
            next_step = f"Run {sync_ep} and verify /api/v1/control/integrations/health."
        else:
            next_step = f"Connect via {connect_ep} with token, then run {sync_ep}."
        items.append(
            {
                "key": key,
                "label": label,
                "connected": connected,
                "connect_endpoint": connect_ep,
                "status_endpoint": status_ep,
                "sync_endpoint": sync_ep,
                "next_step": next_step,
            }
        )
    ready_count = sum(1 for item in items if bool(item["connected"]))
    return IntegrationSetupGuideRead(
        generated_at=now,
        ready_count=ready_count,
        total_count=len(items),
        items=items,  # type: ignore[arg-type]
    )


# ── Google Calendar (literal prefix — must be before /{integration_id}/…) ─────

# ── Nested Integration Routers ────────────────────────────────────────────────


router.include_router(integrations_clickup.router)
router.include_router(integrations_github.router)
router.include_router(integrations_digitalocean.router)
router.include_router(integrations_slack.router)
router.include_router(integrations_perplexity.router)
router.include_router(integrations_linkedin.router)
router.include_router(integrations_notion.router)
router.include_router(integrations_stripe.router)
router.include_router(integrations_google_analytics.router)
router.include_router(integrations_calendly.router)
router.include_router(integrations_elevenlabs.router)
router.include_router(integrations_hubspot.router)
router.include_router(integrations_google_calendar.router)
router.include_router(integrations_whatsapp.router)
router.include_router(integrations_ai.router)

@router.get("/token-health")
async def token_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict[str, object]:
    return await get_rotation_report(db, int(actor["org_id"]))


@router.post("/token-rotate/{integration_type}")
async def token_rotate(
    integration_type: str = fastapi.Path(..., max_length=50, pattern=r"^[a-z][a-z0-9_-]*$"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict[str, object]:
    return await rotate_oauth_token(db, int(actor["org_id"]), integration_type)


@router.get("/security-center")
async def security_center(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict[str, object]:
    org_id = int(actor["org_id"])
    payload = await trend_telemetry.get_security_center(db, org_id)
    trend_payload = trend_telemetry.compute_security_risk_payload(payload)
    await trend_telemetry.record_trend_event(
        db,
        org_id=org_id,
        event_type=trend_telemetry.SECURITY_EVENT,
        payload_json=trend_payload,
        actor_user_id=int(actor["id"]),
        entity_type="integration_security",
        throttle_minutes=15,
    )
    return payload


@router.get("/security-center/trend", response_model=SecurityCenterTrendRead)
async def security_center_trend(
    limit: int = Query(14, ge=2, le=60),
    cursor: str | None = Query(None, max_length=128),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> SecurityCenterTrendRead:
    rows, next_cursor = await trend_telemetry.read_trend_events(
        db,
        org_id=int(actor["org_id"]),
        event_type=trend_telemetry.SECURITY_EVENT,
        limit=limit,
        cursor=cursor,
    )
    points: list[SecurityCenterTrendPointRead] = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        level = str(payload.get("risk_level", "low")).lower()
        if level not in {"low", "medium", "high"}:
            level = "low"
        try:
            score = int(payload.get("risk_score", 0))
        except (TypeError, ValueError):
            score = 0
        points.append(
            SecurityCenterTrendPointRead(
                timestamp=row.created_at,
                risk_score=score,
                risk_level=level,
            )
        )
    return SecurityCenterTrendRead(points=points, next_cursor=next_cursor)


@router.post("/{integration_id}/disconnect", response_model=IntegrationRead)
async def disconnect_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationRead:
    item = await integration_service.disconnect_integration(
        db,
        integration_id=integration_id,
        organization_id=actor["org_id"],
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    await record_action(
        db,
        event_type="integration_disconnected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"type": item.type, "status": item.status},
    )
    return redact_integration_fn(item)


@router.post("/{integration_id}/test", response_model=IntegrationTestResult)
async def test_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationTestResult:
    item = await integration_service.get_integration(
        db,
        integration_id=integration_id,
        organization_id=actor["org_id"],
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Integration not found")

    status = "ok"
    message = "Connection test passed"
    if item.status != "connected":
        status = "failed"
        message = "Integration is disconnected"
    elif item.type == "google_calendar":
        access_token = item.config_json.get("access_token")
        refresh_token = item.config_json.get("refresh_token")
        calendar_id = item.config_json.get("calendar_id", "primary")
        if not access_token:
            status = "failed"
            message = "Missing access_token in config_json for google_calendar"
        else:
            try:
                await list_events_for_day(
                    access_token=access_token,
                    day=datetime.now(UTC).date(),
                    calendar_id=calendar_id,
                )
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
                logger.warning(
                    "Google Calendar connection test failed org=%s integration_id=%s: %s: %s",
                    actor["org_id"],
                    item.id,
                    type(exc).__name__,
                    str(exc)[:300],
                )
                if refresh_token and settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
                    try:
                        refresh = await refresh_access_token(
                            refresh_token=refresh_token,
                            client_id=settings.GOOGLE_CLIENT_ID,
                            client_secret=settings.GOOGLE_CLIENT_SECRET,
                        )
                        new_access_token = refresh.get("access_token")
                        if not new_access_token:
                            raise ValueError("Missing access_token in refresh response")
                        item.config_json = {**item.config_json, "access_token": new_access_token}
                        db.add(item)
                        await integration_service.mark_sync_time(db, item)
                        status = "ok"
                        message = "Connection test passed after token refresh"
                    except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as refresh_exc:
                        logger.warning(
                            "Google Calendar token refresh failed org=%s integration_id=%s: %s: %s",
                            actor["org_id"],
                            item.id,
                            type(refresh_exc).__name__,
                            str(refresh_exc)[:300],
                        )
                        status = "failed"
                        message = safe_provider_error_fn("Google Calendar test failed after token refresh")
                else:
                    status = "failed"
                    message = "Google Calendar test failed and no refresh token is available"
    elif item.type == "whatsapp_business":
        access_token = item.config_json.get("access_token")
        phone_number_id = item.config_json.get("phone_number_id")
        if not access_token or not phone_number_id:
            status = "failed"
            message = "Missing access_token or phone_number_id in config_json for whatsapp_business"
        else:
            try:
                await get_phone_number_details(
                    access_token=str(access_token),
                    phone_number_id=str(phone_number_id),
                )
            except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
                logger.warning(
                    "WhatsApp Business connection test failed org=%s integration_id=%s: %s: %s",
                    actor["org_id"],
                    item.id,
                    type(exc).__name__,
                    str(exc)[:300],
                )
                status = "failed"
                message = safe_provider_error_fn("WhatsApp Business test failed")

    if status == "ok":
        await integration_service.mark_sync_time(db, item)

    await record_action(
        db,
        event_type="integration_tested",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"type": item.type, "result": status, "message": message},
    )
    return IntegrationTestResult(
        integration_id=item.id,
        status=status,  # type: ignore[arg-type]
        message=message,
    )
