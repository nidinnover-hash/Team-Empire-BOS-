"""
Field-level encryption for OAuth tokens stored in the DB.

All OAuth access_token / refresh_token values in Integration.config_json
are encrypted with Fernet before write and decrypted on read.

Key derivation: SHA-256 of SECRET_KEY → 32 bytes → base64url → Fernet key.

WARNING: Rotating SECRET_KEY invalidates all stored tokens. If you rotate
SECRET_KEY, you must re-run the encrypt_integration_tokens migration.
"""

import base64
import hashlib
from typing import cast

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_TOKEN_FIELDS = ("access_token", "refresh_token")


def _fernet() -> Fernet:
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
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
            except (InvalidToken, Exception):
                # Pre-migration plaintext value — leave as-is.
                pass
    return result
