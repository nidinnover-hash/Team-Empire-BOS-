"""
MFA (TOTP) management endpoints.

  GET  /mfa/status      — is MFA enabled for the current user?
  POST /mfa/setup       — generate a new TOTP secret (returns secret + QR)
  POST /mfa/confirm     — verify first code to activate MFA
  POST /mfa/disable     — verify current code then disable MFA
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_api_user, get_db
from app.core.rbac import require_roles
from app.schemas.mfa import (
    MFAConfirmRequest,
    MFADisableRequest,
    MFASetupResponse,
    MFAStatusResponse,
)
from app.services import mfa as mfa_service
from app.services import user as user_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mfa", tags=["MFA"])


@router.get("/status", response_model=MFAStatusResponse)
async def mfa_status(
    current_user: dict = Depends(get_current_api_user),
    db: AsyncSession = Depends(get_db),
):
    """Return whether MFA is currently enabled for the authenticated user."""
    user = await user_service.get_user_by_id(db, current_user["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return MFAStatusResponse(mfa_enabled=bool(user.mfa_enabled))


@router.post("/setup", response_model=MFASetupResponse)
async def mfa_setup(
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new TOTP secret for the authenticated user.
    The secret is NOT saved yet — call /mfa/confirm with a valid code to activate.
    Returns the provisioning URI and an optional inline QR code PNG (data: URI).
    """
    user = await user_service.get_user_by_id(db, current_user["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is already enabled. Disable it first to re-enroll.",
        )

    secret = mfa_service.generate_secret()
    # Store pending secret in a session-scoped key — we embed it in the response
    # and re-validate it in /mfa/confirm. The user MUST confirm before it's saved.
    provisioning_uri = mfa_service.get_provisioning_uri(secret, user.email)
    qr_data_uri = mfa_service.get_qr_data_uri(secret, user.email)

    # Temporarily store the pending secret on the user record (not yet enabled)
    # so /mfa/confirm can verify against it.
    user.totp_secret = secret
    user.mfa_enabled = False
    db.add(user)
    await db.commit()

    return MFASetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri,
        qr_data_uri=qr_data_uri,
    )


@router.post("/confirm", status_code=status.HTTP_200_OK)
async def mfa_confirm(
    body: MFAConfirmRequest,
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm MFA setup by verifying the first code from the authenticator app.
    On success, sets mfa_enabled=True.
    """
    from app.logs.audit import record_action

    user = await user_service.get_user_by_id(db, current_user["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA setup. Call /mfa/setup first.",
        )
    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MFA is already active.",
        )

    if not mfa_service.verify_code(user.totp_secret, body.totp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code. Check your authenticator app and try again.",
        )

    user.mfa_enabled = True
    db.add(user)
    await db.commit()

    await record_action(
        db=db,
        event_type="mfa_enabled",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_type="user",
        entity_id=user.id,
        payload_json={"method": "totp"},
    )

    logger.info("MFA enabled for user id=%d", user.id)
    return {"status": "ok", "message": "MFA enabled successfully."}


@router.post("/disable", status_code=status.HTTP_200_OK)
async def mfa_disable(
    body: MFADisableRequest,
    current_user: dict = Depends(require_roles("CEO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Disable MFA for the authenticated user after verifying current TOTP code.
    Requires a valid code to prevent accidental/malicious disabling.
    """
    from app.logs.audit import record_action

    user = await user_service.get_user_by_id(db, current_user["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not enabled.",
        )
    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No TOTP secret found.",
        )

    if not mfa_service.verify_code(user.totp_secret, body.totp_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code.",
        )

    user.mfa_enabled = False
    user.totp_secret = None
    db.add(user)
    await db.commit()

    await record_action(
        db=db,
        event_type="mfa_disabled",
        actor_user_id=user.id,
        organization_id=user.organization_id,
        entity_type="user",
        entity_id=user.id,
        payload_json={"method": "totp"},
    )

    logger.info("MFA disabled for user id=%d", user.id)
    return {"status": "ok", "message": "MFA disabled."}
