"""Shared helpers for web routes — authentication, JWT, purpose resolution."""

import asyncio
import hashlib
import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.middleware import (
    check_login_allowed,
    clear_login_failures,
    record_login_failure,
)
from app.core.purpose import resolve_login_profile
from app.core.security import create_access_token, hash_password, verify_password
from app.services import org_membership as org_membership_service
from app.services import user as user_service

logger = logging.getLogger(__name__)

# Dummy hash — always run verify_password even when user doesn't exist
# so response time doesn't reveal valid usernames (timing-safe).
_DUMMY_HASH = "pbkdf2_sha256$600000$w7gXiGr39+vmLFhN19GF2g==$2Fr/fvindUecCaX736N+jixutyVFXfjWvTN8w18qRAY="


def _username_fingerprint(username: str) -> str:
    normalized = (username or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


def effective_token_expiry_minutes() -> int:
    session_cap_minutes = max(1, int(settings.ACCOUNT_SESSION_MAX_HOURS)) * 60
    return min(int(settings.ACCESS_TOKEN_EXPIRE_MINUTES), session_cap_minutes)


def enforce_password_login_policy() -> None:
    """Raise 403 if password login is disabled by SSO policy."""
    if settings.ACCOUNT_SSO_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password login is disabled: SSO is required by policy.",
        )


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
    client_ip: str,
    endpoint: str,
    totp_code: str | None = None,
):
    """Shared authentication logic for /token and /web/login.

    Runs PBKDF2 in a thread to avoid blocking the event loop.
    Returns the User ORM object on success, raises HTTPException on failure.

    If the user has MFA enabled:
      - totp_code=None  → raises 401 with X-MFA-Required: true header
      - totp_code wrong → raises 401
      - totp_code valid → proceeds normally
    """
    from app.logs.audit import record_action

    if not check_login_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )
    user = await user_service.get_user_by_email(db, username)

    # Per-account lockout check (supplements per-IP check above)
    if user is not None:
        from app.core.account_security import check_account_locked
        if await check_account_locked(db, user):
            raise HTTPException(
                status_code=423,
                detail="Account temporarily locked due to repeated failed login attempts. Try again later.",
            )

    # Constant-time: always run PBKDF2 so response time doesn't leak
    # whether the username exists.  Use the real hash when available,
    # otherwise the dummy hash, so the crypto work is always performed.
    hash_to_verify = (
        user.password_hash
        if (user is not None and user.is_active)
        else _DUMMY_HASH
    )
    valid = await asyncio.to_thread(verify_password, password, hash_to_verify)
    if user is None or not user.is_active:
        valid = False

    # Transparent rehash: upgrade old iteration counts to current OWASP minimum.
    if valid and user is not None:
        try:
            _scheme, iter_str, *_ = user.password_hash.split("$", 3)
            if _scheme == "pbkdf2_sha256" and int(iter_str) < 600_000:
                user.password_hash = await asyncio.to_thread(hash_password, password)
                db.add(user)
                await db.commit()
                logger.info("Rehashed password for user %d", user.id)
        except (ValueError, TypeError, SQLAlchemyError):
            logger.debug("Password rehash skipped for user %d", user.id, exc_info=True)

    if not valid:
        record_login_failure(client_ip)
        # Per-account failure tracking
        if user is not None:
            from app.core.account_security import record_account_login_failure
            await record_account_login_failure(db, user)
        username_fp = _username_fingerprint(username)
        logger.warning("Failed login from %s on %s", client_ip, endpoint)
        await record_action(
            db,
            event_type="login_failed",
            actor_user_id=user.id if user else None,
            organization_id=user.organization_id if user else 0,
            entity_type="user",
            entity_id=user.id if user else None,
            payload_json={"username_fingerprint": username_fp, "ip": client_ip, "endpoint": endpoint},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/password",
        )

    assert user is not None

    # MFA check: if user has TOTP enabled, require a valid code
    if getattr(user, "mfa_enabled", False):
        if not totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="MFA code required",
                headers={"X-MFA-Required": "true"},
            )
        from app.services.mfa import verify_code as verify_totp
        if not verify_totp(user.totp_secret or "", totp_code):
            record_login_failure(client_ip)
            await record_action(
                db,
                event_type="login_failed_mfa",
                actor_user_id=user.id,
                organization_id=user.organization_id,
                entity_type="user",
                entity_id=user.id,
                payload_json={"ip": client_ip, "endpoint": endpoint},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA code",
            )

    clear_login_failures(client_ip)
    # Clear per-account lockout on success
    from app.core.account_security import reset_account_login_failures
    await reset_account_login_failures(db, user)
    await record_action(
        db,
        event_type="login_success",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_type="user",
        entity_id=user.id,
        payload_json={"ip": client_ip, "endpoint": endpoint, "mfa": getattr(user, "mfa_enabled", False)},
    )
    return user


def create_jwt(
    user,
    *,
    mfa_bootstrap: bool = False,
    org_id: int | None = None,
    role: str | None = None,
) -> str:
    """Create a JWT token for the authenticated user."""
    purpose_profile = resolve_login_profile_cached(user.email)
    token_version = int(getattr(user, "token_version", 1) or 1)
    effective_org_id = int(org_id if org_id is not None else user.organization_id)
    effective_role = str(role or user.role)
    return create_access_token(
        {
            "id": user.id,
            "email": user.email,
            "role": effective_role,
            "org_id": effective_org_id,
            "token_version": token_version,
            "purpose": purpose_profile["purpose"],
            "default_theme": purpose_profile["default_theme"],
            "default_avatar_mode": purpose_profile["default_avatar_mode"],
            "mfa_bootstrap": mfa_bootstrap,
        },
        expires_minutes=10 if mfa_bootstrap else effective_token_expiry_minutes(),
    )


async def resolve_login_organization(
    db: AsyncSession,
    *,
    user,
    requested_org_id: int | None,
) -> tuple[int, str]:
    organizations = await org_membership_service.list_user_accessible_orgs(db, user=user)
    if not organizations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active organization access for this user",
        )
    by_org_id = {int(str(item["id"])): item for item in organizations}
    if requested_org_id is not None:
        selected = by_org_id.get(int(requested_org_id))
        if selected is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Requested organization is not accessible for this user",
            )
        return int(str(selected["id"])), str(selected["role"])

    require_explicit_selection = bool(settings.ACCOUNT_REQUIRE_ORG_SELECTION_ALWAYS) or len(organizations) > 1
    if require_explicit_selection:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "org_selection_required",
                "message": "Select an organization to continue",
                "organizations": organizations,
            },
        )

    selected = organizations[0]
    return int(str(selected["id"])), str(selected["role"])


def resolve_login_profile_cached(email: str) -> dict[str, str]:
    return resolve_login_profile(email)


def read_avatar_scope(user: dict[str, Any], requested_mode: str) -> str:
    if requested_mode == "strategy":
        return "strategy"
    if not settings.PURPOSE_STRICT_BARRIERS:
        return requested_mode
    purpose = str(user.get("purpose") or "professional").strip().lower()
    if purpose == "professional":
        return "professional"
    if purpose == "entertainment":
        return "entertainment"
    if purpose == "personal":
        if requested_mode in {"personal", "professional"}:
            return requested_mode
        return "personal"
    return "professional"


def write_avatar_scope(user: dict[str, Any], requested_mode: str) -> str:
    if requested_mode == "strategy":
        return "strategy"
    if not settings.PURPOSE_STRICT_BARRIERS:
        return requested_mode
    purpose = str(user.get("purpose") or "professional").strip().lower()
    if purpose == "personal":
        return "personal"
    if purpose in {"professional", "entertainment"}:
        return purpose
    return "professional"
