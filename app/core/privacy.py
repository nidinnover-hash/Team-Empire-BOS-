import ipaddress
import re
from typing import Any

from app.core.config import settings
from app.core.sensitive_keys import is_sensitive_key

REDACTED = "***"
_MAX_DEPTH = 8

_PII_EXACT_KEYS = {
    "email",
    "username",
    "to",
    "from",
    "to_address",
    "from_address",
    "phone",
    "phone_number",
    "display_phone_number",
    "ip",
}
_DATA_CLASSIFICATION: dict[str, str] = {
    **{
        k: "secret"
        for k in (
            "access_token",
            "refresh_token",
            "id_token",
            "api_key",
            "authorization",
            "password",
            "secret",
            "client_secret",
            "cookie",
            "set_cookie",
            "webhook_verify_token",
            "pc_session",
            "pc_csrf",
        )
    },
    **{k: "pii" for k in _PII_EXACT_KEYS},
}

_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]{1,64})@([A-Za-z0-9.-]+\.[A-Za-z]{2,63})\b")
_PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{7,}\d")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+\b")
_TOKENISH_RE = re.compile(r"\b[A-Za-z0-9._\-]{32,}\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _privacy_profile() -> str:
    return settings.PRIVACY_POLICY_PROFILE


def _mask_pii_enabled() -> bool:
    profile = _privacy_profile()
    if profile == "strict":
        return True
    if profile == "debug":
        return False
    return settings.PRIVACY_MASK_PII


def _classify_key(key: str) -> str | None:
    return _DATA_CLASSIFICATION.get(key.strip().lower())


def _mask_email(value: str) -> str:
    if "@" not in value:
        return REDACTED
    local, domain = value.split("@", 1)
    if not local:
        return REDACTED
    return f"{local[0]}***@{domain}"


def _mask_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 4:
        return REDACTED
    return f"***{digits[-2:]}"


def _mask_ip(value: str) -> str:
    try:
        ip = ipaddress.ip_address(value.strip())
    except ValueError:
        return REDACTED
    if isinstance(ip, ipaddress.IPv4Address):
        parts = value.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.x"
        return "x.x.x.x"
    # Keep only /64 prefix visibility for IPv6
    exploded = ip.exploded.split(":")
    return ":".join(exploded[:4]) + ":xxxx:xxxx:xxxx:xxxx"


def _sanitize_string(value: str) -> str:
    def _mask_tokenish(match: re.Match[str]) -> str:
        token = match.group(0)
        has_alpha = any(ch.isalpha() for ch in token)
        has_digit = any(ch.isdigit() for ch in token)
        return REDACTED if has_alpha and has_digit else token

    out = value
    if _mask_pii_enabled():
        out = _EMAIL_RE.sub(lambda m: _mask_email(f"{m.group(1)}@{m.group(2)}"), out)
        out = _PHONE_RE.sub(lambda m: _mask_phone(m.group(0)), out)
        if _privacy_profile() == "strict":
            out = _IP_RE.sub(lambda m: _mask_ip(m.group(0)), out)
    out = _BEARER_RE.sub("Bearer ***", out)
    out = _TOKENISH_RE.sub(_mask_tokenish, out)
    max_chars = settings.PRIVACY_AUDIT_MAX_VALUE_CHARS
    if len(out) > max_chars:
        return out[:max_chars] + "...[truncated]"
    return out


def _sanitize_value(value: Any, key_hint: str | None, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return REDACTED
    if key_hint and is_sensitive_key(key_hint):
        return REDACTED
    if isinstance(value, dict):
        return {
            str(k): _sanitize_value(v, key_hint=str(k), depth=depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(v, key_hint=key_hint, depth=depth + 1) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_value(v, key_hint=key_hint, depth=depth + 1) for v in value]
    if isinstance(value, str):
        key = (key_hint or "").lower()
        if _mask_pii_enabled():
            if key in {"email", "username", "to", "from", "to_address", "from_address"}:
                return _mask_email(value)
            if key in {"phone", "phone_number", "display_phone_number"}:
                return _mask_phone(value)
            if key == "ip":
                return _mask_ip(value)
            if _classify_key(key) == "pii" and "@" in value:
                return _mask_email(value)
        return _sanitize_string(value)
    return value


def sanitize_audit_payload(payload: dict | None) -> dict:
    """
    Redact secrets/PII from audit payloads before persisting to DB.
    """
    if not payload:
        return {}
    if not settings.PRIVACY_REDACTION_ENABLED:
        return dict(payload)
    safe = _sanitize_value(dict(payload), key_hint=None, depth=0)
    return safe if isinstance(safe, dict) else {}


def sanitize_response_payload(payload: Any) -> Any:
    """
    Redact/mask sensitive values before returning data in API responses.
    This protects against historical rows created before privacy guards existed.
    """
    if not settings.PRIVACY_RESPONSE_SANITIZATION_ENABLED:
        return payload
    return _sanitize_value(payload, key_hint=None, depth=0)
