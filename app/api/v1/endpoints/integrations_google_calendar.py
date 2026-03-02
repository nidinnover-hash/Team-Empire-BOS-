from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.integrations_shared import (
    calendar_redirect_uri,
    redact_integration,
    sign_google_calendar_state,
    verify_google_calendar_state,
)
from app.core.config import settings
from app.core.deps import get_db
from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.oauth_nonce import consume_oauth_nonce_once
from app.core.oauth_state import verify_oauth_state
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    CalendarEventRead,
    CalendarSyncResult,
    GoogleAuthUrlRead,
    GoogleOAuthCallbackRequest,
    IntegrationRead,
)
from app.services import integration as integration_service
from app.services.calendar_service import get_calendar_events_from_context, sync_calendar_events
from app.tools.google_calendar import (
    build_google_auth_url,
    exchange_code_for_tokens,
)

router = APIRouter(tags=["Integrations"])


def _sign_google_calendar_state(org_id: int) -> str:
    """Compatibility helper used by tests/callers."""
    return sign_google_calendar_state(org_id)


@router.get("/google-calendar/auth-url", response_model=GoogleAuthUrlRead)
async def google_calendar_auth_url(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GoogleAuthUrlRead:
    redir = calendar_redirect_uri()
    if not settings.GOOGLE_CLIENT_ID or not redir:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    state = sign_google_calendar_state(int(actor["org_id"]))
    return GoogleAuthUrlRead(
        auth_url=build_google_auth_url(
            client_id=settings.GOOGLE_CLIENT_ID,
            redirect_uri=redir,
            state=state,
        ),
        state=state,
    )


@router.post("/google-calendar/oauth/callback", response_model=IntegrationRead)
async def google_calendar_oauth_callback(
    request: Request,
    data: GoogleOAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationRead:
    from app.core.middleware import check_per_route_rate_limit, get_client_ip

    if not check_per_route_rate_limit(get_client_ip(request), "gcal_oauth_cb", max_requests=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many OAuth callback attempts. Try again later.")
    redir = calendar_redirect_uri()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not redir:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    verify_google_calendar_state(data.state, expected_org_id=int(actor["org_id"]))
    if not consume_oauth_nonce_once(namespace="gcal_oauth", nonce=data.state, max_age_seconds=600):
        raise HTTPException(status_code=409, detail="OAuth callback already processed (replay rejected)")

    tokens = await exchange_code_for_tokens(
        code=data.code,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=redir,
    )
    existing = await integration_service.get_integration_by_type(db, actor["org_id"], "google_calendar")
    existing_cfg = existing.config_json if existing else {}
    refresh_token = tokens.get("refresh_token") or existing_cfg.get("refresh_token")
    config_json = {
        "access_token": tokens.get("access_token"),
        "refresh_token": refresh_token,
        "token_type": tokens.get("token_type"),
        "scope": tokens.get("scope"),
        "expires_in": tokens.get("expires_in"),
        "calendar_id": data.calendar_id,
        "connected_at": datetime.now(UTC).isoformat(),
    }
    item = await integration_service.connect_integration(
        db,
        organization_id=actor["org_id"],
        integration_type="google_calendar",
        config_json=config_json,
    )
    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"type": item.type, "status": item.status, "oauth": True},
    )
    return redact_integration(item)


@router.get("/google-calendar/oauth/callback", include_in_schema=False, response_model=None)
async def google_calendar_oauth_callback_redirect(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    from app.core.middleware import check_per_route_rate_limit, get_client_ip

    if not check_per_route_rate_limit(get_client_ip(request), "gcal_oauth_cb", max_requests=10, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many OAuth callback attempts. Try again later.")
    redir = calendar_redirect_uri()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not redir:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")

    org_id = verify_oauth_state(state, namespace="gcal_oauth", max_age_seconds=600)
    if not consume_oauth_nonce_once(namespace="gcal_oauth", nonce=state, max_age_seconds=600):
        raise HTTPException(status_code=409, detail="OAuth callback already processed (replay rejected)")

    tokens = await exchange_code_for_tokens(
        code=code,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=redir,
    )
    existing = await integration_service.get_integration_by_type(db, org_id, "google_calendar")
    existing_cfg = existing.config_json if existing else {}
    refresh_token = tokens.get("refresh_token") or existing_cfg.get("refresh_token")
    config_json = {
        "access_token": tokens.get("access_token"),
        "refresh_token": refresh_token,
        "token_type": tokens.get("token_type"),
        "scope": tokens.get("scope"),
        "expires_in": tokens.get("expires_in"),
        "calendar_id": "primary",
        "connected_at": datetime.now(UTC).isoformat(),
    }
    await integration_service.connect_integration(
        db,
        organization_id=org_id,
        integration_type="google_calendar",
        config_json=config_json,
    )
    accepts = (request.headers.get("accept") or "").lower()
    if "text/html" in accepts:
        return RedirectResponse(url="/web/integrations?google_calendar=connected", status_code=303)
    return {"status": "connected", "message": "Google Calendar connected successfully"}


@router.post("/google-calendar/sync", response_model=CalendarSyncResult)
async def sync_google_calendar(
    for_date: date | None = Query(None, description="Date to sync (defaults to today, YYYY-MM-DD)"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CalendarSyncResult:
    scope = f"calendar_sync:{actor['org_id']}:{for_date or date.today()}"
    fingerprint = build_fingerprint({"org_id": int(actor["org_id"]), "for_date": str(for_date or date.today())})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return CalendarSyncResult.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail="Idempotency conflict: this key was already used with a different request body",
            ) from exc

    result = await sync_calendar_events(
        db,
        organization_id=actor["org_id"],
        target_date=for_date,
    )
    if result["error"]:
        raise HTTPException(status_code=400, detail=result["error"])
    await record_action(
        db,
        event_type="calendar_synced",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={"date": result["date"], "synced": result["synced"]},
    )
    response = CalendarSyncResult(date=result["date"], synced=result["synced"])
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response


@router.get("/google-calendar/events", response_model=list[CalendarEventRead])
async def list_calendar_events(
    for_date: date | None = Query(None, description="Date to fetch (defaults to today)"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[CalendarEventRead]:
    entries = await get_calendar_events_from_context(
        db,
        organization_id=actor["org_id"],
        for_date=for_date,
    )
    return [
        CalendarEventRead(
            id=e.id,
            date=str(e.date),
            content=e.content,
            location=e.related_to,
        )
        for e in entries
    ]
