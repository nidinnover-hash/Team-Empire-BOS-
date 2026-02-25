from __future__ import annotations

from app.core.config import settings


def split_emails(raw: str) -> set[str]:
    return {item.strip().lower() for item in (raw or "").split(",") if item.strip()}


def resolve_login_profile(email: str) -> dict[str, str]:
    normalized = (email or "").strip().lower()
    personal = split_emails(settings.PURPOSE_PERSONAL_EMAILS)
    entertainment = split_emails(settings.PURPOSE_ENTERTAINMENT_EMAILS)
    if normalized in entertainment:
        return {
            "purpose": "entertainment",
            "default_theme": settings.PURPOSE_DEFAULT_THEME_ENTERTAINMENT,
            "default_avatar_mode": "entertainment",
        }
    if normalized in personal:
        return {
            "purpose": "personal",
            "default_theme": settings.PURPOSE_DEFAULT_THEME_PERSONAL,
            "default_avatar_mode": "personal",
        }
    return {
        "purpose": "professional",
        "default_theme": settings.PURPOSE_DEFAULT_THEME_PROFESSIONAL,
        "default_avatar_mode": "professional",
    }
