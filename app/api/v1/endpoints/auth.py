import asyncio
import hashlib
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_api_user, get_db
from app.core.middleware import (
    check_login_allowed,
    clear_login_failures,
    get_client_ip,
    record_login_failure,
)
from app.core.purpose import resolve_login_profile
from app.core.security import create_access_token, hash_password, verify_password
from app.logs.audit import record_action
from app.schemas.auth import TokenResponse, UserMeRead
from app.services import user as user_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

# Dummy hash — always run verify_password even when user doesn't exist
# so response time doesn't reveal valid usernames (timing-safe).
_DUMMY_HASH = "pbkdf2_sha256$600000$w7gXiGr39+vmLFhN19GF2g==$2Fr/fvindUecCaX736N+jixutyVFXfjWvTN8w18qRAY="


def _effective_token_expiry_minutes() -> int:
    session_cap_minutes = max(1, int(settings.ACCOUNT_SESSION_MAX_HOURS)) * 60
    return min(int(settings.ACCESS_TOKEN_EXPIRE_MINUTES), session_cap_minutes)


def _username_fingerprint(username: str) -> str:
    normalized = (username or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def _enforce_password_login_policy() -> None:
    # Password login is incompatible with strict SSO-only mode.
    if settings.ACCOUNT_SSO_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password login is disabled: SSO is required by policy.",
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    username: str = Form(..., min_length=3, max_length=254),
    password: str = Form(..., min_length=8, max_length=128),
    db: AsyncSession = Depends(get_db),
):
    _enforce_password_login_policy()
    client_ip = get_client_ip(request)
    if not check_login_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )
    user = await user_service.get_user_by_email(db, username)

    # Constant-time: always run PBKDF2 so response time doesn't leak
    # whether the username exists.
    if user is None or not user.is_active:
        await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
        valid = False
    else:
        valid = await asyncio.to_thread(verify_password, password, user.password_hash)

    # Transparent rehash: upgrade old iteration counts to current OWASP minimum.
    if valid and user is not None:
        try:
            _scheme, iter_str, *_ = user.password_hash.split("$", 3)
            if _scheme == "pbkdf2_sha256" and int(iter_str) < 600_000:
                user.password_hash = await asyncio.to_thread(hash_password, password)
                db.add(user)
                await db.commit()
                logger.info("Rehashed password for user %d (%s → 600k iterations)", user.id, iter_str)
        except (ValueError, TypeError, RuntimeError):
            logger.debug("Password rehash skipped for user %d", user.id, exc_info=True)

    if not valid:
        record_login_failure(client_ip)
        username_fp = _username_fingerprint(username)
        logger.warning("Failed login attempt username_fp=%s from %s", username_fp, client_ip)
        await record_action(
            db,
            event_type="login_failed",
            actor_user_id=user.id if user else None,
            organization_id=user.organization_id if user else 0,
            entity_type="user",
            entity_id=user.id if user else None,
            payload_json={"username_fingerprint": username_fp, "ip": client_ip},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/password",
        )
    assert user is not None
    purpose_profile = resolve_login_profile(user.email)
    access_token = create_access_token(
        {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "org_id": user.organization_id,
            "token_version": int(getattr(user, "token_version", 1) or 1),
            "purpose": purpose_profile["purpose"],
            "default_theme": purpose_profile["default_theme"],
            "default_avatar_mode": purpose_profile["default_avatar_mode"],
        },
        expires_minutes=_effective_token_expiry_minutes(),
    )
    clear_login_failures(client_ip)
    await record_action(
        db,
        event_type="login_success",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_type="user",
        entity_id=user.id,
        payload_json={"ip": client_ip, "endpoint": "/api/v1/auth/login"},
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserMeRead)
async def me(user: dict = Depends(get_current_api_user)):
    return user
