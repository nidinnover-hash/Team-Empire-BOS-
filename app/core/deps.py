import hmac
import logging
import re
from collections.abc import AsyncGenerator
from typing import TypedDict

from fastapi import Cookie, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, oauth2_scheme
from app.db.session import AsyncSessionLocal
from app.models.org_membership import OrganizationMembership
from app.models.user import User
from app.services import api_key as api_key_service
from app.services import api_quota as api_quota_service
from app.services import workspace as workspace_service

logger = logging.getLogger(__name__)

_MFA_BOOTSTRAP_ALLOWED_PREFIXES = (
    "/api/v1/mfa/",
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/me",
)
_MFA_BOOTSTRAP_ALLOWED_WEB_PATHS = {
    "/web/logout",
    "/web/session",
}


class ActorDict(TypedDict):
    id: int
    email: str
    role: str
    org_id: int
    token_version: int
    purpose: str
    default_theme: str | None
    default_avatar_mode: str | None
    auth_type: str
    api_key_id: int | None
    api_key_scopes: list[str]


def _claim_as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _claim_as_str(value: object) -> str | None:
    if isinstance(value, str):
        raw = value.strip()
        return raw if raw else None
    return None


def _parse_api_key_scopes(raw_scopes: object) -> list[str]:
    if not isinstance(raw_scopes, str):
        return []
    parts = [part.strip().lower() for part in raw_scopes.split(",") if part.strip()]
    # Preserve order for observability, dedupe for matching.
    seen: set[str] = set()
    ordered: list[str] = []
    for scope in parts:
        if scope in seen:
            continue
        seen.add(scope)
        ordered.append(scope)
    return ordered


_API_SCOPE_RESOURCE_RE = re.compile(r"^[a-z0-9_]+$")


def _normalize_scope_resource(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _required_api_scope_for_request(request: Request) -> tuple[str, str]:
    action = "read" if request.method in {"GET", "HEAD", "OPTIONS"} else "write"
    path = request.url.path or ""

    # Root authenticated profile endpoint.
    if path == "/me":
        return ("auth", action)

    # Default fallback for unexpected paths.
    resource = "api"
    prefix = "/api/v1/"
    if path.startswith(prefix):
        remainder = path[len(prefix):]
        first_segment = remainder.split("/", 1)[0].strip().lower()
        if first_segment:
            resource = _normalize_scope_resource(first_segment)

    return (resource, action)


def _api_key_allows_scope(raw_scopes: object, required_scope: str, *, request: Request) -> bool:
    scopes = _parse_api_key_scopes(raw_scopes)
    if not scopes:
        return False
    if "*" in scopes:
        return True
    if required_scope.lower() in scopes:
        return True
    resource, action = _required_api_scope_for_request(request)
    if action in scopes:
        return True
    scoped_action = f"{resource}:{action}"
    scoped_all = f"{resource}:*"
    if scoped_action in scopes or scoped_all in scopes:
        return True
    # Backward-compatible acceptance for keys that still use "api:read/write".
    if f"api:{action}" in scopes or "api:*" in scopes:
        return True
    # Defensive guard: reject malformed dynamic resources.
    if not _API_SCOPE_RESOURCE_RE.match(resource):
        return False
    return False


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one DB session per request, always closed on exit."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_api_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> ActorDict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload: dict[str, object] | None = None
    try:
        payload = decode_access_token(token)
    except ValueError:
        payload = None

    if payload is None:
        key = await api_key_service.validate_api_key(db, token)
        if key is None:
            logger.warning("Token decode and API key validation failed")
            raise credentials_exception
        result = await db.execute(
            select(User).where(
                User.id == int(key.user_id),
                User.organization_id == int(key.organization_id),
            )
        )
        db_user = result.scalar_one_or_none()
        if db_user is None or not bool(db_user.is_active):
            logger.warning("API key rejected key_id=%s reason=%s", key.id, "inactive_user")
            raise credentials_exception
        required_scope = "read" if request.method in {"GET", "HEAD", "OPTIONS"} else "write"
        resource, action = _required_api_scope_for_request(request)
        if not _api_key_allows_scope(key.scopes, required_scope, request=request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have the required permissions for this operation",
            )
        try:
            allowed, used, limit = await api_quota_service.consume_api_request_quota(
                db,
                organization_id=int(db_user.organization_id),
            )
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "API key daily request quota exceeded for this organization. "
                        f"Used {used}/{limit} requests today."
                    ),
                )
        except HTTPException:
            raise
        except (SQLAlchemyError, RuntimeError, ValueError, TypeError) as exc:
            logger.warning("API quota check failed; denying request: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API quota service temporarily unavailable. Please retry shortly.",
            ) from exc
        return {
            "id": int(db_user.id),
            "email": str(db_user.email),
            "role": str(db_user.role),
            "org_id": int(db_user.organization_id),
            "token_version": int(getattr(db_user, "token_version", 1)),
            "purpose": "professional",
            "default_theme": None,
            "default_avatar_mode": None,
            "auth_type": "api_key",
            "api_key_id": int(key.id),
            "api_key_scopes": _parse_api_key_scopes(key.scopes),
        }

    user_id_raw = payload.get("id")
    email = payload.get("email")
    org_id_raw = payload.get("org_id")
    user_id = _claim_as_int(user_id_raw)
    org_id = _claim_as_int(org_id_raw)
    if user_id is None or email is None or org_id is None:
        logger.warning(
            "Token missing required claims: id=%s email=%s org_id=%s",
            user_id_raw,
            email is not None,
            org_id_raw,
        )
        raise credentials_exception
    token_version = _claim_as_int(payload.get("token_version", 1)) or 1

    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one_or_none()
    org_mismatch = False
    token_version_mismatch = False
    effective_role = _claim_as_str(payload.get("role")) or str(getattr(db_user, "role", "STAFF"))
    if db_user is not None:
        if int(db_user.organization_id) == org_id:
            org_mismatch = False
            effective_role = str(getattr(db_user, "role", effective_role))
        else:
            membership_result = await db.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == org_id,
                    OrganizationMembership.user_id == int(db_user.id),
                    OrganizationMembership.is_active.is_(True),
                )
            )
            membership = membership_result.scalar_one_or_none()
            org_mismatch = membership is None
            if membership is not None:
                effective_role = str(membership.role)
        token_version_mismatch = int(getattr(db_user, "token_version", 1)) != token_version
    if (
        db_user is None
        or not bool(db_user.is_active)
        or org_mismatch
        or token_version_mismatch
    ):
        if db_user is None:
            reason = "not_found"
        elif not bool(getattr(db_user, "is_active", False)):
            reason = "inactive"
        elif org_mismatch:
            reason = "org_mismatch"
        elif token_version_mismatch:
            reason = "token_version_mismatch"
        else:
            reason = "mismatch"
        logger.warning("API auth rejected user_id=%s reason=%s org_id=%s", user_id, reason, org_id)
        raise credentials_exception
    if bool(payload.get("mfa_bootstrap")) and not any(
        request.url.path.startswith(prefix) for prefix in _MFA_BOOTSTRAP_ALLOWED_PREFIXES
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA enrollment required before accessing this endpoint",
        )
    return {
        "id": int(db_user.id),
        "email": str(db_user.email),
        "role": effective_role,
        "org_id": int(org_id),
        "token_version": int(getattr(db_user, "token_version", 1)),
        "purpose": _claim_as_str(payload.get("purpose")) or "professional",
        "default_theme": _claim_as_str(payload.get("default_theme")),
        "default_avatar_mode": _claim_as_str(payload.get("default_avatar_mode")),
        "auth_type": "user",
        "api_key_id": None,
        "api_key_scopes": [],
    }


def get_current_org_id(user: ActorDict = Depends(get_current_api_user)) -> int:
    return int(user["org_id"])


async def get_current_web_user(
    request: Request,
    session_token: str | None = Cookie(default=None, alias="pc_session"),
    db: AsyncSession = Depends(get_db),
) -> ActorDict:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    try:
        payload = decode_access_token(session_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc
    user_id_raw = payload.get("id")
    org_id_raw = payload.get("org_id")
    user_id = _claim_as_int(user_id_raw)
    org_id = _claim_as_int(org_id_raw)
    if user_id is None or org_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session payload")
    token_version = _claim_as_int(payload.get("token_version", 1)) or 1
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one_or_none()
    effective_role = _claim_as_str(payload.get("role")) or "STAFF"
    org_allowed = False
    if db_user is not None and int(db_user.organization_id) == org_id:
        org_allowed = True
        effective_role = str(getattr(db_user, "role", effective_role))
    elif db_user is not None:
        membership_result = await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.user_id == int(db_user.id),
                OrganizationMembership.is_active.is_(True),
            )
        )
        membership = membership_result.scalar_one_or_none()
        org_allowed = membership is not None
        if membership is not None:
            effective_role = str(membership.role)

    if (
        db_user is None
        or not bool(db_user.is_active)
        or not org_allowed
        or int(getattr(db_user, "token_version", 1)) != token_version
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    if bool(payload.get("mfa_bootstrap")) and request.url.path not in _MFA_BOOTSTRAP_ALLOWED_WEB_PATHS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA enrollment required before accessing web features",
        )
    return {
        "id": int(db_user.id),
        "email": str(db_user.email),
        "role": effective_role,
        "org_id": int(org_id),
        "token_version": int(getattr(db_user, "token_version", 1)),
        "purpose": _claim_as_str(payload.get("purpose")) or "professional",
        "default_theme": _claim_as_str(payload.get("default_theme")),
        "default_avatar_mode": _claim_as_str(payload.get("default_avatar_mode")),
        "auth_type": "user",
        "api_key_id": None,
        "api_key_scopes": [],
    }


def verify_csrf(
    csrf_cookie: str | None = Cookie(default=None, alias="pc_csrf"),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if csrf_cookie is None or csrf_header is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF token")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


async def get_current_workspace_id(
    request: Request,
    workspace_id_query: int | None = Query(default=None, alias="workspace_id"),
    workspace_id_header: int | None = Header(default=None, alias="X-Workspace-Id"),
    actor: ActorDict = Depends(get_current_api_user),
    db: AsyncSession = Depends(get_db),
) -> int:
    """
    Resolve active workspace context for the request.

    Sources:
    - `X-Workspace-Id` header
    - `workspace_id` query parameter
    - org default workspace (created lazily if missing)
    """
    if workspace_id_header is not None and workspace_id_query is not None and workspace_id_header != workspace_id_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace mismatch between header and query parameter",
        )

    workspace_id = workspace_id_header if workspace_id_header is not None else workspace_id_query
    if workspace_id is None:
        default_ws = await workspace_service.ensure_default_workspace(db, int(actor["org_id"]))
        workspace_id = int(default_ws.id)

    allowed = await workspace_service.user_can_access_workspace(
        db,
        workspace_id=int(workspace_id),
        org_id=int(actor["org_id"]),
        user_id=int(actor["id"]),
        actor_role=str(actor["role"]),
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace access denied",
        )
    return int(workspace_id)
