import hmac
import logging
from collections.abc import AsyncGenerator
from typing import TypedDict

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, oauth2_scheme
from app.db.session import AsyncSessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)


class ActorDict(TypedDict):
    id: int
    email: str
    role: str
    org_id: int
    token_version: int
    purpose: str
    default_theme: str | None
    default_avatar_mode: str | None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one DB session per request, always closed on exit."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_api_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        logger.warning("Token decode failed: %s", type(exc).__name__)
        raise credentials_exception from exc

    user_id = payload.get("id")
    email = payload.get("email")
    org_id = payload.get("org_id")
    if user_id is None or email is None or org_id is None:
        logger.warning("Token missing required claims: id=%s email=%s org_id=%s", user_id, email is not None, org_id)
        raise credentials_exception
    token_version = int(payload.get("token_version", 1) or 1)

    result = await db.execute(select(User).where(User.id == int(user_id)))
    db_user = result.scalar_one_or_none()
    org_mismatch = False
    email_mismatch = False
    token_version_mismatch = False
    if db_user is not None:
        org_mismatch = int(db_user.organization_id) != int(org_id)
        email_mismatch = str(db_user.email).strip().lower() != str(email).strip().lower()
        token_version_mismatch = int(getattr(db_user, "token_version", 1)) != token_version
    if (
        db_user is None
        or not bool(db_user.is_active)
        or org_mismatch
        or email_mismatch
        or token_version_mismatch
    ):
        if db_user is None:
            reason = "not_found"
        elif not bool(getattr(db_user, "is_active", False)):
            reason = "inactive"
        elif org_mismatch:
            reason = "org_mismatch"
        elif email_mismatch:
            reason = "email_mismatch"
        elif token_version_mismatch:
            reason = "token_version_mismatch"
        else:
            reason = "mismatch"
        logger.warning("API auth rejected user_id=%s reason=%s org_id=%s", user_id, reason, org_id)
        raise credentials_exception
    return {
        "id": int(db_user.id),
        "email": str(db_user.email),
        "role": str(db_user.role),
        "org_id": int(db_user.organization_id),
        "token_version": int(getattr(db_user, "token_version", 1)),
        "purpose": payload.get("purpose", "professional"),
        "default_theme": payload.get("default_theme"),
        "default_avatar_mode": payload.get("default_avatar_mode"),
    }


def get_current_org_id(user: dict = Depends(get_current_api_user)) -> int:
    return int(user["org_id"])


async def get_current_web_user(
    session_token: str | None = Cookie(default=None, alias="pc_session"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    try:
        payload = decode_access_token(session_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc
    user_id = payload.get("id")
    org_id = payload.get("org_id")
    email = payload.get("email")
    if user_id is None or org_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session payload")
    token_version = int(payload.get("token_version", 1) or 1)
    result = await db.execute(select(User).where(User.id == int(user_id)))
    db_user = result.scalar_one_or_none()
    if (
        db_user is None
        or not bool(db_user.is_active)
        or int(db_user.organization_id) != int(org_id)
        or str(db_user.email).strip().lower() != str(email or "").strip().lower()
        or int(getattr(db_user, "token_version", 1)) != token_version
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return {
        "id": int(db_user.id),
        "email": str(db_user.email),
        "role": str(db_user.role),
        "org_id": int(db_user.organization_id),
        "token_version": int(getattr(db_user, "token_version", 1)),
        "purpose": payload.get("purpose", "professional"),
        "default_theme": payload.get("default_theme"),
        "default_avatar_mode": payload.get("default_avatar_mode"),
    }


def verify_csrf(
    csrf_cookie: str | None = Cookie(default=None, alias="pc_csrf"),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> None:
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
