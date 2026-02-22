import secrets
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    AIProviderStatus,
    AITestResult,
    CalendarEventRead,
    CalendarSyncResult,
    GoogleAuthUrlRead,
    GoogleOAuthCallbackRequest,
    IntegrationConnectRequest,
    IntegrationRead,
    IntegrationTestResult,
)
from app.services import integration as integration_service
from app.services.calendar_service import (
    get_calendar_events_from_context,
    sync_calendar_events,
)
from app.tools.google_calendar import (
    build_google_auth_url,
    exchange_code_for_tokens,
    list_events_for_day,
    refresh_access_token,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


def _safe_provider_error(prefix: str) -> str:
    return f"{prefix}. Reconnect integration and retry."


def _redact_integration(item: IntegrationRead | object) -> IntegrationRead:
    data = IntegrationRead.model_validate(item).model_dump()
    config = dict(data["config_json"])
    for key in ("access_token", "refresh_token", "client_secret"):
        if key in config:
            config[key] = "***"
    data["config_json"] = config
    return IntegrationRead(**data)


# ── Collection endpoints (no path params) ─────────────────────────────────────

@router.get("", response_model=list[IntegrationRead])
async def list_integrations(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[IntegrationRead]:
    items = await integration_service.list_integrations(db, organization_id=actor["org_id"])
    return [_redact_integration(item) for item in items]


@router.post("/connect", response_model=IntegrationRead, status_code=201)
async def connect_integration(
    data: IntegrationConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationRead:
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
    return _redact_integration(item)


# ── Google Calendar (literal prefix — must be before /{integration_id}/…) ─────

@router.get("/google-calendar/auth-url", response_model=GoogleAuthUrlRead)
async def google_calendar_auth_url(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GoogleAuthUrlRead:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    state = f"org:{actor['org_id']}:{secrets.token_urlsafe(24)}"
    return GoogleAuthUrlRead(
        auth_url=build_google_auth_url(
            client_id=settings.GOOGLE_CLIENT_ID,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            state=state,
        ),
        state=state,
    )


@router.post("/google-calendar/oauth/callback", response_model=IntegrationRead)
async def google_calendar_oauth_callback(
    data: GoogleOAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationRead:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    expected_prefix = f"org:{actor['org_id']}:"
    if not data.state.startswith(expected_prefix):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    tokens = await exchange_code_for_tokens(
        code=data.code,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )
    # Preserve existing refresh_token — Google only returns it on first consent
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
        "connected_at": datetime.now(timezone.utc).isoformat(),
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
    return _redact_integration(item)


@router.post("/google-calendar/sync", response_model=CalendarSyncResult)
async def sync_google_calendar(
    for_date: date | None = Query(None, description="Date to sync (defaults to today, YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CalendarSyncResult:
    """
    Fetch Google Calendar events and store them as daily context entries.
    Events appear automatically in briefings and AI memory.
    """
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
    return CalendarSyncResult(date=result["date"], synced=result["synced"])


@router.get("/google-calendar/events", response_model=list[CalendarEventRead])
async def list_calendar_events(
    for_date: date | None = Query(None, description="Date to fetch (defaults to today)"),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> list[CalendarEventRead]:
    """List synced calendar events for a date from local storage."""
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


# ── AI Provider (literal prefix — must be before /{integration_id}/…) ─────────

_PLACEHOLDER_KEYS = {"sk-your-key-here", "sk-xxxxxxxxxxxxxxxxxxxxxxxx", "", "your-anthropic-key-here"}


def _key_is_configured(key: str | None) -> bool:
    return bool(key) and key not in _PLACEHOLDER_KEYS


@router.get("/ai/status", response_model=list[AIProviderStatus])
async def ai_provider_status(
    _actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[AIProviderStatus]:
    """
    Check which AI providers (OpenAI, Anthropic) are configured and active.
    Does NOT make a live API call — just inspects the current settings.
    """
    active = settings.DEFAULT_AI_PROVIDER
    return [
        AIProviderStatus(
            provider="openai",
            configured=_key_is_configured(settings.OPENAI_API_KEY),
            active=(active == "openai"),
            model=settings.AGENT_MODEL_OPENAI,
        ),
        AIProviderStatus(
            provider="anthropic",
            configured=_key_is_configured(settings.ANTHROPIC_API_KEY),
            active=(active == "anthropic"),
            model=settings.AGENT_MODEL_ANTHROPIC,
        ),
        AIProviderStatus(
            provider="groq",
            configured=_key_is_configured(settings.GROQ_API_KEY),
            active=(active == "groq"),
            model=settings.AGENT_MODEL_GROQ,
        ),
    ]


@router.post("/ai/test", response_model=AITestResult)
async def test_ai_provider(
    provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> AITestResult:
    """
    Make a live test call to OpenAI or Anthropic.

    - provider: "openai" or "anthropic". Defaults to DEFAULT_AI_PROVIDER.
    - Returns the provider's response to a simple ping prompt.
    """
    from app.services.ai_router import call_ai

    chosen = provider or settings.DEFAULT_AI_PROVIDER

    if chosen == "openai" and not _key_is_configured(settings.OPENAI_API_KEY):
        return AITestResult(
            provider="openai",
            status="not_configured",
            message="OPENAI_API_KEY is missing or is still a placeholder in .env",
        )
    if chosen == "anthropic" and not _key_is_configured(settings.ANTHROPIC_API_KEY):
        return AITestResult(
            provider="anthropic",
            status="not_configured",
            message="ANTHROPIC_API_KEY is missing or is still a placeholder in .env",
        )

    response = await call_ai(
        system_prompt="You are a connection test. Respond with exactly: 'Connected.'",
        user_message="ping",
        provider=chosen,
        max_tokens=20,
    )

    # call_ai never raises — error strings start with "Error:"
    if response.startswith("Error:"):
        await record_action(
            db,
            event_type="ai_test_failed",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"provider": chosen, "error": response},
        )
        return AITestResult(provider=chosen, status="failed", message=response)

    await record_action(
        db,
        event_type="ai_test_passed",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={"provider": chosen},
    )
    return AITestResult(
        provider=chosen,
        status="ok",
        message=f"{chosen.capitalize()} is connected and responding.",
        sample_response=response,
    )


# ── Parametric endpoints (/{integration_id}/…) — MUST be last ─────────────────

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
    return _redact_integration(item)


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
                    day=datetime.now(timezone.utc).date(),
                    calendar_id=calendar_id,
                )
            except Exception:
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
                    except Exception:
                        status = "failed"
                        message = _safe_provider_error("Google Calendar test failed after token refresh")
                else:
                    status = "failed"
                    message = "Google Calendar test failed and no refresh token is available"

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
        status=status,
        message=message,
    )
