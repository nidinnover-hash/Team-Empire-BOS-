import hmac
import json
import logging
from datetime import UTC, date, datetime
from hashlib import sha256

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import (
    integrations_calendly,
    integrations_clickup,
    integrations_digitalocean,
    integrations_elevenlabs,
    integrations_github,
    integrations_google_analytics,
    integrations_hubspot,
    integrations_linkedin,
    integrations_notion,
    integrations_perplexity,
    integrations_slack,
    integrations_stripe,
)
from app.api.v1.endpoints.integrations_shared import (
    GENERIC_CONNECT_ALLOWED_TYPES,
    GENERIC_CONNECT_BLOCKED_ROUTES,
    calendar_redirect_uri,
    redact_integration,
    safe_provider_error,
    sign_google_calendar_state,
    verify_google_calendar_state,
)
from app.core.config import PLACEHOLDER_AI_KEYS, settings
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
    AIProviderConnectRequest,
    AIProviderConnectResult,
    AIProviderName,
    AIProviderStatus,
    AITestResult,
    CalendarEventRead,
    CalendarSyncResult,
    CodingProjectDiscoveryRead,
    GoogleAuthUrlRead,
    GoogleOAuthCallbackRequest,
    IntegrationConnectRequest,
    IntegrationRead,
    IntegrationSetupGuideRead,
    IntegrationTestResult,
    WhatsAppSendRequest,
    WhatsAppSendResult,
)
from app.services import integration as integration_service
from app.services import whatsapp_service
from app.services.calendar_service import (
    get_calendar_events_from_context,
    sync_calendar_events,
)
from app.services.token_health import get_rotation_report, rotate_oauth_token
from app.tools.google_calendar import (
    build_google_auth_url,
    exchange_code_for_tokens,
    list_events_for_day,
    refresh_access_token,
)
from app.tools.whatsapp_business import get_phone_number_details, send_text_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["Integrations"])

_GENERIC_CONNECT_ALLOWED_TYPES = GENERIC_CONNECT_ALLOWED_TYPES
_GENERIC_CONNECT_BLOCKED_ROUTES = GENERIC_CONNECT_BLOCKED_ROUTES
safe_provider_error_fn = safe_provider_error
sign_google_calendar_state_fn = sign_google_calendar_state
verify_google_calendar_state_fn = verify_google_calendar_state
redact_integration_fn = redact_integration


def _sign_google_calendar_state(org_id: int) -> str:
    """Compatibility wrapper used by legacy tests/callers."""
    return sign_google_calendar_state_fn(org_id)


def _first_phone_number_id(payload: dict) -> str | None:
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict):
                continue
            raw_phone = metadata.get("phone_number_id")
            if isinstance(raw_phone, str) and raw_phone.strip():
                return raw_phone.strip()
    return None


async def _resolve_whatsapp_context(
    db: AsyncSession,
    payload: dict,
) -> tuple[int | None, int | None, str | None]:
    phone_number_id = _first_phone_number_id(payload)
    if not phone_number_id:
        return None, None, None
    integration = await integration_service.find_whatsapp_integration_by_phone_number_id(
        db,
        phone_number_id=phone_number_id,
    )
    if integration is None:
        return None, None, phone_number_id
    return int(integration.organization_id), int(integration.id), phone_number_id


async def _record_whatsapp_webhook_failure(
    db: AsyncSession,
    *,
    organization_id: int | None,
    integration_id: int | None,
    phone_number_id: str | None,
    error_code: str,
    detail: str,
) -> None:
    if organization_id is None:
        return
    await record_action(
        db=db,
        event_type="whatsapp_webhook_failed",
        actor_user_id=None,
        organization_id=organization_id,
        entity_type="integration",
        entity_id=integration_id,
        payload_json={
            "error_code": error_code,
            "detail": detail,
            "phone_number_id": phone_number_id,
        },
    )


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

@router.get("/google-calendar/auth-url", response_model=GoogleAuthUrlRead)
async def google_calendar_auth_url(
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GoogleAuthUrlRead:
    redir = calendar_redirect_uri()
    if not settings.GOOGLE_CLIENT_ID or not redir:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    state = sign_google_calendar_state_fn(int(actor["org_id"]))
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
    data: GoogleOAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> IntegrationRead:
    redir = calendar_redirect_uri()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not redir:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    verify_google_calendar_state_fn(data.state, expected_org_id=int(actor["org_id"]))
    if not consume_oauth_nonce_once(namespace="gcal_oauth", nonce=data.state, max_age_seconds=600):
        raise HTTPException(status_code=409, detail="OAuth callback already processed (replay rejected)")
    tokens = await exchange_code_for_tokens(
        code=data.code,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=redir,
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
    return redact_integration_fn(item)


@router.get("/google-calendar/oauth/callback", include_in_schema=False, response_model=None)
async def google_calendar_oauth_callback_redirect(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Handle Google OAuth browser redirect for Calendar.
    Google redirects here with ?code=XXX&state=YYY after user grants permission.
    No Bearer token required — org_id is extracted from the signed state.
    """
    redir = calendar_redirect_uri()
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not redir:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")

    # Verify signed state and extract org_id (validates signature + expiry)
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
        return RedirectResponse(
            url="/web/integrations?google_calendar=connected",
            status_code=303,
        )
    return {"status": "connected", "message": "Google Calendar connected successfully"}


@router.post("/google-calendar/sync", response_model=CalendarSyncResult)
async def sync_google_calendar(
    for_date: date | None = Query(None, description="Date to sync (defaults to today, YYYY-MM-DD)"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> CalendarSyncResult:
    """
    Fetch Google Calendar events and store them as daily context entries.
    Events appear automatically in briefings and AI memory.
    """
    scope = f"calendar_sync:{actor['org_id']}:{for_date or date.today()}"
    fingerprint = build_fingerprint(
        {"org_id": int(actor["org_id"]), "for_date": str(for_date or date.today())}
    )
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return CalendarSyncResult.model_validate(cached)
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict: this key was already used with a different request body") from exc
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

def _key_is_configured(key: str | None) -> bool:
    return bool(key) and key not in PLACEHOLDER_AI_KEYS


@router.get("/ai/status", response_model=list[AIProviderStatus])
async def ai_provider_status(
    _actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> list[AIProviderStatus]:
    """
    Check which AI providers are configured and active.
    Checks both .env keys and dashboard-saved keys.
    """
    from app.services.ai_router import _get_key, _key_ok

    org_id = int(_actor["org_id"])
    active = settings.DEFAULT_AI_PROVIDER
    email = settings.EMAIL_AI_PROVIDER or active
    providers = [
        ("openai", settings.AGENT_MODEL_OPENAI),
        ("anthropic", settings.AGENT_MODEL_ANTHROPIC),
        ("groq", settings.AGENT_MODEL_GROQ),
        ("gemini", settings.AGENT_MODEL_GEMINI),
    ]
    return [
        AIProviderStatus(
            provider=name,
            configured=_key_ok(_get_key(name, org_id=org_id)),
            active=(active == name),
            email_active=(email == name),
            model=model,
        )
        for name, model in providers
    ]


_AI_CONNECT_TYPE_MAP: dict[str, str] = {
    "openai": "ai_openai",
    "anthropic": "ai_anthropic",
    "groq": "ai_groq",
    "gemini": "ai_gemini",
}


@router.post("/ai/{provider}/connect", response_model=AIProviderConnectResult, status_code=201)
async def ai_provider_connect(
    provider: AIProviderName,
    data: AIProviderConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> AIProviderConnectResult:
    """
    Save an AI provider API key. Validates with a live test call, then stores
    encrypted in the integration table and updates the in-memory cache.
    """
    from app.services.ai_router import call_ai, set_ai_key_cache

    # Temporarily cache the key so call_ai can use it for the test
    org_id = int(actor["org_id"])
    set_ai_key_cache(provider, data.api_key, org_id=org_id)

    response = await call_ai(
        system_prompt="You are a connection test. Respond with exactly: 'Connected.'",
        user_message="ping",
        provider=provider,
        max_tokens=20,
        organization_id=org_id,
    )

    if response.startswith("Error:"):
        # Rollback cache on failure
        from app.services.ai_router import clear_ai_key_cache
        clear_ai_key_cache(provider, org_id=org_id)
        await record_action(
            db,
            event_type="ai_provider_connect_failed",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"provider": provider, "error": response[:200]},
        )
        raise HTTPException(status_code=400, detail=response)

    # Test passed — persist to integration table
    integration_type = _AI_CONNECT_TYPE_MAP[provider]
    item = await integration_service.connect_integration(
        db,
        organization_id=actor["org_id"],
        integration_type=integration_type,
        config_json={"api_key": data.api_key, "connected_at": datetime.now(UTC).isoformat()},
    )
    await record_action(
        db,
        event_type="ai_provider_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"provider": provider},
    )
    return AIProviderConnectResult(
        provider=provider,
        status="connected",
        message=f"{provider.capitalize()} API key validated and saved.",
    )


@router.post("/ai/{provider}/disconnect")
async def ai_provider_disconnect(
    provider: AIProviderName,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict[str, str]:
    """Clear a cached AI provider key and disconnect the integration record."""
    from app.services.ai_router import clear_ai_key_cache

    clear_ai_key_cache(provider, org_id=int(actor["org_id"]))

    integration_type = _AI_CONNECT_TYPE_MAP[provider]
    existing = await integration_service.get_integration_by_type(
        db, actor["org_id"], integration_type,
    )
    if existing:
        await integration_service.disconnect_integration(
            db, integration_id=existing.id, organization_id=actor["org_id"],
        )
    await record_action(
        db,
        event_type="ai_provider_disconnected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=existing.id if existing else None,
        payload_json={"provider": provider},
    )
    return {"status": "disconnected", "provider": provider}


@router.post("/ai/test", response_model=AITestResult)
async def test_ai_provider(
    provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> AITestResult:
    """
    Make a live test call to OpenAI, Anthropic, Groq, or Gemini.

    - provider: "openai", "anthropic", "groq", or "gemini". Defaults to DEFAULT_AI_PROVIDER.
    - Returns the provider's response to a simple ping prompt.
    """
    from app.services.ai_router import _get_key, _key_ok, call_ai

    chosen = (provider or settings.DEFAULT_AI_PROVIDER or "").strip().lower()
    if chosen == "claude":
        chosen = "anthropic"
    if chosen not in {"openai", "anthropic", "groq", "gemini"}:
        return AITestResult(
            provider=chosen or "unknown",
            status="failed",
            message="Unsupported provider. Use one of: openai, claude, anthropic, groq, gemini.",
        )

    org_id = int(actor["org_id"])
    if not _key_ok(_get_key(chosen, org_id=org_id)):
        return AITestResult(
            provider=chosen,
            status="not_configured",
            message=f"{chosen.upper()} API key is missing. Add it via .env or POST /ai/{chosen}/connect.",
        )

    response = await call_ai(
        system_prompt="You are a connection test. Respond with exactly: 'Connected.'",
        user_message="ping",
        provider=chosen,
        max_tokens=20,
        organization_id=actor["org_id"],
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


@router.get("/ai/coding-discovery", response_model=CodingProjectDiscoveryRead)
async def ai_coding_discovery(
    project_name: str | None = Query(None, max_length=120),
    language: str | None = Query(None, max_length=60),
    stage: str | None = Query(None, max_length=60),
    _actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER", "STAFF")),
) -> CodingProjectDiscoveryRead:
    """
    Return coding-project discovery questions so the clone asks before implementation.
    """
    p = (project_name or "project").strip()
    lang = (language or "stack").strip()
    s = (stage or "planning").strip()
    questions = [
        f"What is the exact outcome you want for {p} in this phase?",
        "What are the top 3 blockers today?",
        f"What tech stack and runtime versions are required ({lang})?",
        "What constraints exist (deadline, budget, infra, compliance)?",
        "What is the current architecture and where does this change fit?",
        "What are the acceptance criteria and measurable success metrics?",
        "What risks are unacceptable (downtime, data loss, security regressions)?",
        "What tests must pass before release?",
        "Who approves production changes and what is rollback plan?",
        "Which tasks can be automated safely vs require manual approval?",
    ]
    next_prompt = (
        f"You are my senior coding assistant for {p}. Current stage: {s}. "
        "Ask concise discovery questions first, then propose an implementation plan "
        "with risks, tests, and rollout steps."
    )
    return CodingProjectDiscoveryRead(
        provider_options=["openai", "claude", "groq", "gemini"],
        questions=questions,
        next_prompt=next_prompt,
    )


@router.post("/whatsapp/send-test", response_model=WhatsAppSendResult)
async def whatsapp_send_test_message(
    data: WhatsAppSendRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> WhatsAppSendResult:
    item = await integration_service.get_integration_by_type(
        db,
        organization_id=actor["org_id"],
        integration_type="whatsapp_business",
    )
    if item is None or item.status != "connected":
        raise HTTPException(status_code=400, detail="WhatsApp Business is not connected")
    if item.organization_id != actor["org_id"]:
        raise HTTPException(status_code=403, detail="Organization mismatch")

    access_token = item.config_json.get("access_token")
    phone_number_id = item.config_json.get("phone_number_id")
    if not access_token or not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="Missing access_token or phone_number_id in whatsapp_business config_json",
        )

    try:
        resp = await send_text_message(
            access_token=str(access_token),
            phone_number_id=str(phone_number_id),
            to=data.to,
            body=data.body,
        )
    except (httpx.HTTPError, RuntimeError, ValueError, TypeError) as exc:
        await record_action(
            db,
            event_type="whatsapp_test_message_failed",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=item.id,
            payload_json={
                "to": data.to,
                "error_code": "provider_send_failed",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=502,
            detail=safe_provider_error_fn("WhatsApp message send failed"),
        ) from exc

    message_id: str | None = None
    messages = resp.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            raw_id = first.get("id")
            if isinstance(raw_id, str):
                message_id = raw_id

    await integration_service.mark_sync_time(db, item)
    await record_action(
        db,
        event_type="whatsapp_test_message_sent",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=item.id,
        payload_json={"to": data.to, "message_id": message_id},
    )

    return WhatsAppSendResult(status="queued", to=data.to, message_id=message_id)


@router.get("/whatsapp/webhook", include_in_schema=False)
async def whatsapp_webhook_verify(
    hub_mode: str | None = Query(None, alias="hub.mode", max_length=50),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token", max_length=500),
    hub_challenge: str | None = Query(None, alias="hub.challenge", max_length=5000),
) -> PlainTextResponse:
    expected = (settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "").strip()
    if (
        hub_mode == "subscribe"
        and hub_verify_token
        and expected
        and hmac.compare_digest(hub_verify_token, expected)
        and hub_challenge is not None
    ):
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp/webhook", include_in_schema=False)
async def whatsapp_webhook_receive(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive webhook events from WhatsApp Business.
    Verifies X-Hub-Signature-256 when WHATSAPP_APP_SECRET is configured.
    Acks quickly - processing pipelines can be added behind this endpoint.
    """
    import json as _json

    _MAX_WEBHOOK_BODY = 1_048_576  # 1 MB guard against oversized payloads

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_WEBHOOK_BODY:
                raise HTTPException(status_code=413, detail="Webhook payload too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc

    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        raise HTTPException(status_code=415, detail="Webhook expects application/json")

    raw_body = await request.body()
    if len(raw_body) > _MAX_WEBHOOK_BODY:
        raise HTTPException(status_code=413, detail="Webhook payload too large")

    try:
        payload = _json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")

    webhook_org_id, webhook_integration_id, webhook_phone_number_id = await _resolve_whatsapp_context(
        db, payload
    )

    app_secret = (settings.WHATSAPP_APP_SECRET or "").strip()
    if not app_secret:
        await _record_whatsapp_webhook_failure(
            db,
            organization_id=webhook_org_id,
            integration_id=webhook_integration_id,
            phone_number_id=webhook_phone_number_id,
            error_code="webhook_disabled_missing_secret",
            detail="WhatsApp webhook disabled: WHATSAPP_APP_SECRET not configured",
        )
        raise HTTPException(
            status_code=503,
            detail="WhatsApp webhook disabled: WHATSAPP_APP_SECRET not configured",
        )

    sig_header = request.headers.get("X-Hub-Signature-256", "")
    expected_sig = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        sha256,
    ).hexdigest()
    if not sig_header or not hmac.compare_digest(sig_header, expected_sig):
        await _record_whatsapp_webhook_failure(
            db,
            organization_id=webhook_org_id,
            integration_id=webhook_integration_id,
            phone_number_id=webhook_phone_number_id,
            error_code="signature_verification_failed",
            detail="Webhook signature verification failed",
        )
        raise HTTPException(status_code=403, detail="Webhook signature verification failed")

    window = max(30, int(settings.WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS))
    if not consume_oauth_nonce_once(
        namespace="whatsapp_webhook_sig",
        nonce=sig_header,
        max_age_seconds=window,
    ):
        await _record_whatsapp_webhook_failure(
            db,
            organization_id=webhook_org_id,
            integration_id=webhook_integration_id,
            phone_number_id=webhook_phone_number_id,
            error_code="webhook_replay_detected",
            detail="Webhook replay detected",
        )
        raise HTTPException(status_code=409, detail="Webhook replay detected")

    entries = payload.get("entry")
    count = len(entries) if isinstance(entries, list) else 0
    telemetry = await whatsapp_service.ingest_webhook_payload(db, payload)
    if webhook_org_id is not None:
        await record_action(
            db=db,
            event_type="whatsapp_webhook_received",
            actor_user_id=None,
            organization_id=webhook_org_id,
            entity_type="integration",
            entity_id=webhook_integration_id,
            payload_json={
                "entries": count,
                "phone_number_id": webhook_phone_number_id,
                **telemetry,
            },
        )
    return {"status": "received", "entries": count, **telemetry}
# ── ClickUp (literal prefix — must be before /{integration_id}/…) ──────────────


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

@router.get("/token-health")
async def token_health(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict[str, object]:
    return await get_rotation_report(db, int(actor["org_id"]))


@router.post("/token-rotate/{integration_type}")
async def token_rotate(
    integration_type: str,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> dict[str, object]:
    return await rotate_oauth_token(db, int(actor["org_id"]), integration_type)


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



