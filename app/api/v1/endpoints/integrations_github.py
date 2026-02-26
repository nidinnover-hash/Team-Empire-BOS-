from typing import cast

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.idempotency import (
    IdempotencyConflictError,
    build_fingerprint,
    get_cached_response,
    store_response,
)
from app.core.rbac import require_roles
from app.core.request_context import get_current_request_id
from app.logs.audit import record_action
from app.schemas.integration import (
    GitHubConnectRequest,
    GitHubInstallationDiscoveryResult,
    GitHubStatusRead,
    GitHubSyncResult,
)
from app.services import github_app_auth, github_service
from app.services import integration as integration_service

router = APIRouter(tags=["Integrations"])


@router.post("/github/connect", response_model=GitHubStatusRead, status_code=201)
async def github_connect(
    data: GitHubConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubStatusRead:
    request_id = get_current_request_id()
    try:
        info = await github_service.connect_github(
            db, org_id=int(actor["org_id"]), api_token=data.api_token
        )
    except (RuntimeError, ValueError, TypeError, TimeoutError, ConnectionError, OSError) as exc:
        import httpx as _httpx

        status_hint = ""
        if isinstance(exc, _httpx.HTTPStatusError):
            code = exc.response.status_code
            if code == 401:
                status_hint = " Token invalid or expired."
            elif code == 403:
                status_hint = " Token missing 'repo' or 'read:user' scope."
            else:
                status_hint = f" GitHub returned HTTP {code}."
        await record_action(
            db,
            event_type="integration_connected",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={
                "type": "github",
                "request_id": request_id,
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=400,
            detail=f"GitHub connection failed.{status_hint} ({type(exc).__name__}). Check your token and scopes.",
        ) from exc

    await record_action(
        db,
        event_type="integration_connected",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=info["id"],
        payload_json={"type": "github", "login": info.get("login"), "request_id": request_id, "status": "ok"},
    )
    return GitHubStatusRead(connected=True, login=info.get("login"), repos_tracked=0)


@router.get("/github/status", response_model=GitHubStatusRead)
async def github_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubStatusRead:
    status = await github_service.get_github_status(db, org_id=int(actor["org_id"]))
    return GitHubStatusRead(**status)


@router.post("/github/discover-installation", response_model=GitHubInstallationDiscoveryResult)
async def github_discover_installation(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubInstallationDiscoveryResult:
    org_login, installation_id = await github_app_auth.discover_installation_for_org()
    existing = await integration_service.get_integration_by_type(db, int(actor["org_id"]), "github")
    cfg = existing.config_json if existing else {}
    cfg["org_login"] = org_login
    cfg["installation_id"] = installation_id
    await integration_service.connect_integration(
        db=db,
        organization_id=int(actor["org_id"]),
        integration_type="github",
        config_json=cfg,
    )
    return GitHubInstallationDiscoveryResult(ok=True, org=org_login, installation_id=installation_id)


@router.post("/github/sync", response_model=GitHubSyncResult)
async def github_sync(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=256),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> GitHubSyncResult:
    org_id = int(actor["org_id"])
    request_id = get_current_request_id()
    scope = f"github_sync:{org_id}"
    fingerprint = build_fingerprint({"org_id": org_id, "action": "github_sync"})
    if idempotency_key:
        try:
            cached = get_cached_response(scope, idempotency_key, fingerprint=fingerprint)
            if cached:
                return cast(GitHubSyncResult, GitHubSyncResult.model_validate(cached))
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail="Idempotency conflict: this key was already used with a different request body") from exc
    result = await github_service.sync_github(db, org_id=org_id)
    if result["error"]:
        await record_action(
            db,
            event_type="github_synced",
            actor_user_id=actor["id"],
            organization_id=actor["org_id"],
            entity_type="integration",
            entity_id=None,
            payload_json={"request_id": request_id, "status": "error", "error": result["error"]},
        )
        raise HTTPException(status_code=400, detail=result["error"])

    await record_action(
        db,
        event_type="github_synced",
        actor_user_id=actor["id"],
        organization_id=actor["org_id"],
        entity_type="integration",
        entity_id=None,
        payload_json={
            "request_id": request_id,
            "status": "ok",
            "prs_synced": result["prs_synced"],
            "issues_synced": result["issues_synced"],
        },
    )
    status = await github_service.get_github_status(db, org_id=org_id)
    response = GitHubSyncResult(
        prs_synced=result["prs_synced"],
        issues_synced=result["issues_synced"],
        last_sync_at=status.get("last_sync_at"),
    )
    if idempotency_key:
        store_response(scope, idempotency_key, response.model_dump(), fingerprint=fingerprint)
    return response
