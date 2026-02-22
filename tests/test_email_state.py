"""
Tests for the Gmail OAuth state signing/verification functions.

Covers:
- New 4-part state format (org:ts:nonce:sig)
- Rejection of old 3-part states (would allow CSRF if accepted)
- Rejection of tampered signatures
- Rejection of expired states
"""
import hmac
import time
from hashlib import sha256

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.email import _sign_email_state, _verify_email_state
from app.core.config import settings


def test_sign_produces_four_part_state():
    state = _sign_email_state(42)
    parts = state.split(":")
    assert len(parts) == 4, "State must be org:ts:nonce:sig"


def test_sign_encodes_correct_org_id():
    state = _sign_email_state(7)
    org_id_str = state.split(":")[0]
    assert org_id_str == "7"


def test_verify_accepts_valid_state():
    state = _sign_email_state(7)
    org_id = _verify_email_state(state)
    assert org_id == 7


def test_verify_different_org_ids():
    for org_id in (1, 42, 999):
        state = _sign_email_state(org_id)
        assert _verify_email_state(state) == org_id


def test_verify_rejects_old_three_part_state():
    """Old format (org:ts:sig) was vulnerable to forgery — must be rejected."""
    ts = int(time.time())
    payload = f"1:{ts}"
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        sha256,
    ).hexdigest()
    old_state = f"{payload}:{sig}"

    with pytest.raises(HTTPException) as exc_info:
        _verify_email_state(old_state)
    assert exc_info.value.status_code == 400


def test_verify_rejects_tampered_signature():
    state = _sign_email_state(1)
    # Replace last character of signature to invalidate it
    last = state[-1]
    tampered = state[:-1] + ("y" if last != "y" else "z")

    with pytest.raises(HTTPException) as exc_info:
        _verify_email_state(tampered)
    assert exc_info.value.status_code == 400


def test_verify_rejects_tampered_org_id():
    """Changing the org_id in the state must invalidate the signature."""
    state = _sign_email_state(1)
    parts = state.split(":", 3)
    parts[0] = "999"  # swap org_id without re-signing
    tampered = ":".join(parts)

    with pytest.raises(HTTPException) as exc_info:
        _verify_email_state(tampered)
    assert exc_info.value.status_code == 400


def test_verify_rejects_expired_state():
    state = _sign_email_state(1)
    # max_age_seconds=-1 forces expiry: age (>=0) > -1 is always True
    with pytest.raises(HTTPException) as exc_info:
        _verify_email_state(state, max_age_seconds=-1)
    assert exc_info.value.status_code == 400


def test_verify_rejects_completely_invalid_state():
    with pytest.raises(HTTPException):
        _verify_email_state("not-a-valid-state-at-all")
