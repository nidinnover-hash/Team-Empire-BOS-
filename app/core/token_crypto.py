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

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.sensitive_keys import is_sensitive_key

_INVALID_FIELDS_KEY = "__invalid_token_fields"
logger = logging.getLogger(__name__)


def _looks_like_fernet(value: str) -> bool:
    return value.startswith("gAAAA")


def _fernet() -> Fernet:
    # Use a dedicated TOKEN_ENCRYPTION_KEY (key separation from JWT SECRET_KEY).
    # In production (DEBUG=False) this is mandatory; in development we fall back
    # to SECRET_KEY with a warning so local dev isn't blocked.
    raw_key = settings.TOKEN_ENCRYPTION_KEY
    if not raw_key:
        if not settings.DEBUG:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY is not configured. Set it in .env to a value "
                'different from SECRET_KEY. Generate: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        logger.warning(
            "TOKEN_ENCRYPTION_KEY not set — falling back to SECRET_KEY. "
            "Set TOKEN_ENCRYPTION_KEY in .env for proper key separation."
        )
        raw_key = settings.SECRET_KEY
    elif raw_key == settings.SECRET_KEY:
        raise ValueError(
            "TOKEN_ENCRYPTION_KEY must differ from SECRET_KEY for key separation"
        )
    key_bytes = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string. Returns a Fernet ciphertext string."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a Fernet ciphertext string.
    Raises InvalidToken if the value is corrupted or encrypted with a different key.
    """
    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def encrypt_config(config_json: dict) -> dict:
    """
    Return a copy of config_json with access_token and refresh_token encrypted.
    Other fields are left untouched.
    """
    result = dict(config_json)
    # Internal diagnostics only; never persist this helper field.
    result.pop(_INVALID_FIELDS_KEY, None)
    for field, current_value in list(result.items()):
        if not isinstance(field, str) or not is_sensitive_key(field):
            continue
        value = current_value
        if not value or not isinstance(value, str):
            continue
        # Normalize accidentally pre-encrypted values before re-encrypting.
        if _looks_like_fernet(value):
            try:
                value = decrypt_token(value)
            except InvalidToken:
                # Treat non-decryptable value as plaintext and re-encrypt under
                # the active key; this repairs malformed storage over time.
                logger.warning(
                    "Token field '%s' looked encrypted but was invalid; re-encrypting raw value",
                    field,
                )
        result[field] = encrypt_token(value)
    return result


def decrypt_config(config_json: dict) -> dict:
    """
    Return a copy of config_json with access_token and refresh_token decrypted.
    Silently skips fields that are already plaintext (pre-migration rows).
    """
    result = dict(config_json)
    invalid_fields: list[str] = []
    for field, current_value in list(result.items()):
        if not isinstance(field, str) or not is_sensitive_key(field):
            continue
        if current_value:
            try:
                result[field] = decrypt_token(str(current_value))
            except InvalidToken:
                # Pre-migration plaintext value — leave as-is.
                value = result.get(field)
                if isinstance(value, str) and _looks_like_fernet(value):
                    logger.warning(
                        "Invalid encrypted integration token for field '%s'; clearing value",
                        field,
                    )
                    result[field] = ""
                    invalid_fields.append(field)
    if invalid_fields:
        result[_INVALID_FIELDS_KEY] = invalid_fields
    return result
