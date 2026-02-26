"""
Shared OAuth state signer / verifier for all OAuth integrations.

Uses OAUTH_STATE_KEY if configured, otherwise falls back to SECRET_KEY.
Includes timestamp expiry and nonce replay protection.
"""
import hmac
import secrets
from hashlib import sha256
from time import time

from fastapi import HTTPException

from app.core.config import settings
from app.core.oauth_nonce import consume_oauth_nonce_once


def _state_key() -> bytes:
    key = (settings.OAUTH_STATE_KEY or settings.SECRET_KEY).strip()
    return key.encode("utf-8")


def sign_oauth_state(org_id: int) -> str:
    """Create a signed, timestamped, nonce-protected state string."""
    ts = int(time())
    nonce = secrets.token_urlsafe(16)
    payload = f"{org_id}:{ts}:{nonce}"
    sig = hmac.new(_state_key(), payload.encode("utf-8"), sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_oauth_state(
    state: str,
    namespace: str,
    max_age_seconds: int = 600,
    expected_org_id: int | None = None,
) -> int:
    """
    Verify and consume an OAuth state string. Returns the org_id.

    Raises HTTPException(400) on any failure.
    """
    try:
        parts = state.split(":", 3)
        if len(parts) != 4:
            raise ValueError("Invalid state format")
        org_id_str, ts_str, nonce, sig = parts
        payload = f"{org_id_str}:{ts_str}:{nonce}"
        expected_sig = hmac.new(_state_key(), payload.encode("utf-8"), sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise ValueError("Invalid state signature")
        if expected_org_id is not None and int(org_id_str) != expected_org_id:
            raise ValueError("State organization mismatch")
        ts = int(ts_str)
        if int(time()) - ts > max_age_seconds:
            raise ValueError("State expired")
        if not consume_oauth_nonce_once(namespace, nonce, max_age_seconds=max_age_seconds):
            raise ValueError("State replayed")
        return int(org_id_str)
    except HTTPException:
        raise
    except (TypeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc
