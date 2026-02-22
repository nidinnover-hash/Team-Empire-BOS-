from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_OPENAI_KEYS = {"", "sk-your-key-here", "sk-xxxxxxxxxxxxxxxxxxxxxxxx"}
PLACEHOLDER_ANTHROPIC_KEYS = {"", "your-anthropic-key-here"}
PLACEHOLDER_GROQ_KEYS = {"", "gsk_your-key-here", "gsk_your_groq_key_here"}
PLACEHOLDER_AI_KEYS = PLACEHOLDER_OPENAI_KEYS | PLACEHOLDER_ANTHROPIC_KEYS | PLACEHOLDER_GROQ_KEYS
_PLACEHOLDER_GOOGLE_VALUES = {"", "replace-me", "your-google-client-id", "your-google-client-secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # silently drop any unrecognized env vars
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/personal_clone"

    # AI providers
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    DEFAULT_AI_PROVIDER: str = "openai"  # openai | anthropic | groq
    AGENT_MODEL_OPENAI: str = "gpt-4o-mini"
    AGENT_MODEL_ANTHROPIC: str = "claude-haiku-4-5-20251001"
    AGENT_MODEL_GROQ: str = "llama-3.3-70b-versatile"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str | None = None

    # Internal API and rate limiting
    CLONE_API_KEY: str | None = None
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 20

    # App
    APP_NAME: str = "Personal Clone"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENFORCE_STARTUP_VALIDATION: bool = False
    AUTO_CREATE_SCHEMA: bool = False
    AUTO_SEED_DEFAULTS: bool = False
    COOKIE_SECURE: bool = False  # Set True in production (requires HTTPS)
    SECRET_KEY: str = "change_me_in_env"
    ADMIN_EMAIL: str = "demo@ai.com"
    ADMIN_PASSWORD: str = "demo"  # Override in .env — never leave 'demo' in production
    ADMIN_NAME: str = "Nidin Nover"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()


def validate_startup_settings(s: Settings) -> list[str]:
    """
    Return startup configuration issues.
    Enforcement is opt-in via ENFORCE_STARTUP_VALIDATION.
    """
    issues: list[str] = []

    provider = (s.DEFAULT_AI_PROVIDER or "").strip().lower()
    if provider == "openai":
        key = (s.OPENAI_API_KEY or "").strip()
        if key in PLACEHOLDER_OPENAI_KEYS:
            issues.append("OPENAI_API_KEY is missing or placeholder while DEFAULT_AI_PROVIDER=openai")
    elif provider == "anthropic":
        key = (s.ANTHROPIC_API_KEY or "").strip()
        if key in PLACEHOLDER_ANTHROPIC_KEYS:
            issues.append("ANTHROPIC_API_KEY is missing or placeholder while DEFAULT_AI_PROVIDER=anthropic")
    elif provider == "groq":
        key = (s.GROQ_API_KEY or "").strip()
        if key in PLACEHOLDER_GROQ_KEYS:
            issues.append("GROQ_API_KEY is missing or placeholder while DEFAULT_AI_PROVIDER=groq")
    else:
        issues.append(f"DEFAULT_AI_PROVIDER has unsupported value: {provider!r}")

    google_id = (s.GOOGLE_CLIENT_ID or "").strip()
    google_secret = (s.GOOGLE_CLIENT_SECRET or "").strip()
    google_redirect = (s.GOOGLE_REDIRECT_URI or "").strip()
    any_google = bool(google_id or google_secret or google_redirect)
    all_google = bool(google_id and google_secret and google_redirect)

    if any_google and not all_google:
        issues.append("Google OAuth config is partial; set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI")
    if google_id in _PLACEHOLDER_GOOGLE_VALUES:
        issues.append("GOOGLE_CLIENT_ID looks like a placeholder")
    if google_secret in _PLACEHOLDER_GOOGLE_VALUES:
        issues.append("GOOGLE_CLIENT_SECRET looks like a placeholder")

    return issues
