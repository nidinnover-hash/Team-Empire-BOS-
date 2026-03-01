"""Web authentication routes: login, logout, session, api-token."""

import logging
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy import update as sa_update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_web_user, get_db, verify_csrf
from app.core.security import create_access_token, decode_access_token
from app.schemas.auth import (
    WebApiTokenResponse,
    WebLoginResponse,
    WebLogoutResponse,
    WebSessionResponse,
    WebSessionUser,
)
from app.web._helpers import (
    authenticate_user,
    create_jwt,
    effective_token_expiry_minutes,
    enforce_password_login_policy,
    resolve_login_profile_cached,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Web Auth"])


@router.post("/web/login", response_model=WebLoginResponse)
async def web_login(
    request: Request,
    response: Response,
    username: str = Form(..., min_length=3, max_length=254),
    password: str = Form(..., min_length=8, max_length=128),
    totp_code: str | None = Form(None, min_length=6, max_length=6),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.core.middleware import get_client_ip

    enforce_password_login_policy()
    client_ip = get_client_ip(request)
    user = await authenticate_user(db, username, password, client_ip, "/web/login", totp_code=totp_code)
    access_token = create_jwt(user)
    purpose_profile = resolve_login_profile_cached(user.email)
    csrf_token = secrets.token_urlsafe(32)
    max_age = effective_token_expiry_minutes() * 60

    # Clear stale cookies before setting new ones (prevents session fixation)
    for cookie_name in ("pc_session", "pc_csrf", "pc_theme_scope", "pc_theme_default", "pc_avatar_default"):
        response.delete_cookie(cookie_name, path="/")

    _cookie_base = dict(
        max_age=max_age,
        samesite="strict",
        secure=settings.COOKIE_SECURE,
        path="/",
    )
    response.set_cookie(key="pc_session", value=access_token, httponly=True, **_cookie_base)
    response.set_cookie(key="pc_csrf", value=csrf_token, httponly=False, **_cookie_base)
    response.set_cookie(key="pc_theme_scope", value=purpose_profile["purpose"], httponly=False, **_cookie_base)
    response.set_cookie(key="pc_theme_default", value=purpose_profile["default_theme"], httponly=False, **_cookie_base)
    response.set_cookie(key="pc_avatar_default", value=purpose_profile["default_avatar_mode"], httponly=False, **_cookie_base)

    # Kick off a background integration sync (throttled, fire-and-forget)
    if settings.SYNC_ENABLED:
        from app.services.sync_scheduler import trigger_sync_for_org
        await trigger_sync_for_org(user.organization_id)

    return {"status": "ok", "email": user.email, "role": user.role}


@router.post("/web/logout", response_model=WebLogoutResponse)
async def web_logout(
    response: Response,
    user: dict = Depends(get_current_web_user),
    _csrf_ok: None = Depends(verify_csrf),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Invalidate only the current authenticated user session lineage.
    try:
        from app.models.user import User
        await db.execute(
            sa_update(User)
            .where(
                User.id == int(user["id"]),
                User.organization_id == int(user["org_id"]),
                User.is_active.is_(True),
            )
            .values(token_version=User.token_version + 1)
        )
        await db.commit()
    except SQLAlchemyError:
        logger.debug("Token version bump failed on logout user_id=%s", user.get("id"), exc_info=True)

    for cookie_name in ("pc_session", "pc_csrf", "pc_theme_scope", "pc_theme_default", "pc_avatar_default"):
        response.delete_cookie(cookie_name, path="/")
    return {"status": "logged_out"}


@router.get("/web/api-token", include_in_schema=False, response_model=WebApiTokenResponse)
async def web_api_token(request: Request, user: dict = Depends(get_current_web_user)) -> dict:
    """Return a fresh Bearer token for the current web session. Used by dashboard JS."""
    from app.core.middleware import check_per_route_rate_limit, get_client_ip
    client_ip = get_client_ip(request)
    if not check_per_route_rate_limit(client_ip, "web_api_token", max_requests=10, window_seconds=60):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many token requests. Please wait.")
    purpose_profile = resolve_login_profile_cached(str(user.get("email", "")))
    purpose = str(user.get("purpose") or purpose_profile["purpose"])
    default_theme = str(user.get("default_theme") or purpose_profile["default_theme"])
    default_avatar_mode = str(user.get("default_avatar_mode") or purpose_profile["default_avatar_mode"])
    web_ttl = max(1, int(settings.WEB_API_TOKEN_EXPIRE_MINUTES))
    token = create_access_token(
        {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "org_id": user["org_id"],
            "token_version": int(user.get("token_version") or 1),
            "purpose": purpose,
            "default_theme": default_theme,
            "default_avatar_mode": default_avatar_mode,
            "web_api": True,
        },
        expires_minutes=min(effective_token_expiry_minutes(), web_ttl),
    )
    return {"token": token}


@router.get("/web/session", response_model=WebSessionResponse)
async def web_session(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    token = request.cookies.get("pc_session")
    if not token:
        return {"logged_in": False}
    try:
        payload = decode_access_token(token)
    except ValueError:
        return {"logged_in": False}
    try:
        user = await get_current_web_user(request=request, session_token=token, db=db)
    except HTTPException:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "user": WebSessionUser(
            id=user.get("id"),
            email=user.get("email"),
            role=user.get("role", "STAFF"),
            org_id=user.get("org_id"),
            purpose=user.get("purpose", "professional"),
            default_theme=payload.get("default_theme", settings.PURPOSE_DEFAULT_THEME_PROFESSIONAL),
            default_avatar_mode=payload.get("default_avatar_mode", "professional"),
        ),
    }
