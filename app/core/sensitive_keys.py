from __future__ import annotations

_SECRET_EXACT_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "api_token",
    "authorization",
    "password",
    "secret",
    "client_secret",
    "private_key",
    "bot_token",
    "cookie",
    "set_cookie",
    "webhook_verify_token",
    "pc_session",
    "pc_csrf",
}

_SECRET_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "cookie",
    "private_key",
)

_SECRET_KEY_EXCEPTIONS = {"token_type"}


def is_sensitive_key(key: str) -> bool:
    k = key.strip().lower()
    if not k:
        return False
    if k in _SECRET_KEY_EXCEPTIONS:
        return False
    if k in _SECRET_EXACT_KEYS:
        return True
    return any(marker in k for marker in _SECRET_KEY_MARKERS)
