import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.integration import (
    GoogleAuthUrlRead,
    GoogleOAuthCallbackRequest,
    IntegrationConnectRequest,
    IntegrationRead,
    IntegrationTestResult,
)
from app.services import integration as integration_service
from app.tools.google_calendar import (
    build_google_auth_url,
    exchange_code_for_tokens,
    list_events_for_day,
    refresh_access_token,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


def _redact_integration(item: IntegrationRead | object) -> IntegrationRead:
    data = IntegrationRead.model_validate(item).model_dump()
    config = dict(data["config_json"])
    for key in ("access_token", "refresh_token", "client_secret"):
        if key in config:
            config[key] = "***"
    data["config_json"] = config
    return IntegrationRead(**data)


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
    config_json = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
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
                        await integration_service.mark_sync_time(db, item)
                        status = "ok"
                        message = "Connection test passed after token refresh"
                    except Exception as refresh_exc:
                        status = "failed"
                        message = f"Google Calendar test failed: {refresh_exc}"
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
