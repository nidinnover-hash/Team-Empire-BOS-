"""
TOTP MFA service — RFC 6238 / Google Authenticator compatible.

Uses pyotp for TOTP generation and verification. The raw base32 secret is
stored in User.totp_secret. Encrypt it at the model layer using the same
TOKEN_ENCRYPTION_KEY Fernet key if you want field-level encryption (future).

Current threat model: secret is in the DB, which is protected by access controls
and the DB is not public. This is acceptable for a single-user self-hosted app.
"""
from __future__ import annotations

import base64
import io
import logging

logger = logging.getLogger(__name__)

# Clock drift window: how many 30-second periods to accept on either side.
# window=1 means ±30 seconds (standard recommendation).
_TOTP_WINDOW = 1
_TOTP_DIGITS = 6
_TOTP_INTERVAL = 30  # seconds
_ISSUER = "NidinClone"


def generate_secret() -> str:
    """Generate a new random base32 TOTP secret (20 bytes = 32 base32 chars)."""
    import pyotp
    return str(pyotp.random_base32())


def get_provisioning_uri(secret: str, email: str, issuer: str = _ISSUER) -> str:
    """Return otpauth:// URI for QR code generation (Google Authenticator format)."""
    import pyotp
    totp = pyotp.TOTP(secret, digits=_TOTP_DIGITS, interval=_TOTP_INTERVAL)
    return str(totp.provisioning_uri(name=email, issuer_name=issuer))


def get_qr_data_uri(secret: str, email: str) -> str | None:
    """
    Return a data: URI for the QR code PNG.
    Returns None if qrcode package is not installed (optional dependency).
    """
    try:
        import qrcode
        uri = get_provisioning_uri(secret, email)
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{b64}"
    except ImportError:
        logger.debug("qrcode package not installed; QR PNG unavailable")
        return None
    except Exception as exc:
        logger.warning("QR code generation failed: %s", type(exc).__name__)
        return None


def verify_code(secret: str, code: str) -> bool:
    """
    Verify a 6-digit TOTP code against the stored secret.
    Returns True if valid (within ±1 window period).
    """
    if not secret or not code:
        return False
    # Normalise: strip whitespace and spaces (users sometimes type "123 456")
    code = code.replace(" ", "").strip()
    if len(code) != _TOTP_DIGITS or not code.isdigit():
        return False
    try:
        import pyotp
        totp = pyotp.TOTP(secret, digits=_TOTP_DIGITS, interval=_TOTP_INTERVAL)
        return bool(totp.verify(code, valid_window=_TOTP_WINDOW))
    except Exception as exc:
        logger.warning("TOTP verification error: %s", type(exc).__name__)
        return False
