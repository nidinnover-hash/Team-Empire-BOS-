"""
Field-level encryption for OAuth tokens stored in the DB.

All OAuth access_token / refresh_token values in Integration.config_json
are encrypted with Fernet before write and decrypted on read.

Key derivation:
  If TOKEN_ENCRYPTION_KEY is set in .env (recommended), it is used as the
  master secret (SHA-256 → 32 bytes → base64url → Fernet key).
  Otherwise falls back to SECRET_KEY for backward compatibility.

  IMPORTANT: Use a *different* value for TOKEN_ENCRYPTION_KEY than SECRET_KEY
  so that rotating the JWT signing key does not invalidate stored OAuth tokens.

WARNING: Rotating the active key invalidates all stored tokens.
"""

import base64
import hashlib
import logging
from typing import cast

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_TOKEN_FIELDS = ("access_token", "refresh_token", "api_token")
logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    # Use a dedicated TOKEN_ENCRYPTION_KEY when available (key separation).
    # Falls back to SECRET_KEY so existing encrypted tokens remain readable.
    raw_key = settings.TOKEN_ENCRYPTION_KEY or settings.SECRET_KEY
    key_bytes = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns a Fernet ciphertext string."""
    return cast(str, _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8"))


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a Fernet ciphertext string.
    Raises InvalidToken if the value is corrupted or encrypted with a different key.
    """
    return cast(str, _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8"))


def encrypt_config(config_json: dict) -> dict:
    """
    Return a copy of config_json with access_token and refresh_token encrypted.
    Other fields are left untouched.
    """
    result = dict(config_json)
    for field in _TOKEN_FIELDS:
        if result.get(field):
            result[field] = encrypt_token(result[field])
    return result


def decrypt_config(config_json: dict) -> dict:
    """
    Return a copy of config_json with access_token and refresh_token decrypted.
    Silently skips fields that are already plaintext (pre-migration rows).
    """
    result = dict(config_json)
    for field in _TOKEN_FIELDS:
        if result.get(field):
            try:
                result[field] = decrypt_token(result[field])
            except InvalidToken:
                # Pre-migration plaintext value — leave as-is.
                value = result.get(field)
                if isinstance(value, str) and value.startswith("gAAAA"):
                    logger.warning("Invalid encrypted integration token for field '%s'; leaving value unchanged", field)
    return result
