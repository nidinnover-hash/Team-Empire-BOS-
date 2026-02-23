from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_OPENAI_KEYS = {"", "sk-your-key-here", "sk-xxxxxxxxxxxxxxxxxxxxxxxx"}
PLACEHOLDER_ANTHROPIC_KEYS = {"", "your-anthropic-key-here"}
PLACEHOLDER_GROQ_KEYS = {"", "gsk_your-key-here", "gsk_your_groq_key_here"}
PLACEHOLDER_AI_KEYS = PLACEHOLDER_OPENAI_KEYS | PLACEHOLDER_ANTHROPIC_KEYS | PLACEHOLDER_GROQ_KEYS
_PLACEHOLDER_GOOGLE_VALUES = {"", "replace-me", "your-google-client-id", "your-google-client-secret"}
AIProvider = Literal["openai", "anthropic", "groq"]
IdempotencyBackend = Literal["auto", "memory", "redis"]
AppMode = Literal["NIDIN_AI", "EMPIREO_AI"]


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
    DEFAULT_AI_PROVIDER: AIProvider = "openai"
    AGENT_MODEL_OPENAI: str = "gpt-4o-mini"
    AGENT_MODEL_ANTHROPIC: str = "claude-haiku-4-5-20251001"
    AGENT_MODEL_GROQ: str = "llama-3.3-70b-versatile"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str | None = None

    # Internal API and rate limiting
    WHATSAPP_APP_SECRET: str | None = None   # Used to verify X-Hub-Signature-256 on webhook POSTs
    WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS: int = 300
    CLONE_API_KEY: str | None = None
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 20
    IDEMPOTENCY_BACKEND: IdempotencyBackend = "auto"
    IDEMPOTENCY_REDIS_URL: str | None = None
    IDEMPOTENCY_REDIS_PREFIX: str = "pc:idempotency"
    IDEMPOTENCY_TTL_SECONDS: int = 60 * 30
    IDEMPOTENCY_MAX_ITEMS: int = 5_000

    # App
    APP_NAME: str = "Personal Clone"
    APP_MODE: AppMode = "NIDIN_AI"
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    # Separate key for Fernet token encryption (Integration.config_json).
    # If not set, falls back to a SHA-256 derivative of SECRET_KEY (legacy behaviour).
    # Set this to a different random 32-byte hex value to achieve key separation.
    TOKEN_ENCRYPTION_KEY: str | None = None
    PRIVACY_REDACTION_ENABLED: bool = True
    PRIVACY_MASK_PII: bool = True
    PRIVACY_RESPONSE_SANITIZATION_ENABLED: bool = True
    PRIVACY_AUDIT_MAX_VALUE_CHARS: int = 200
    CLONE_AUTO_LEARN_FROM_CHAT: bool = True

    # Background sync scheduler
    SYNC_ENABLED: bool = True
    SYNC_INTERVAL_MINUTES: int = 30   # how often the scheduler fires
    SYNC_THROTTLE_MINUTES: int = 15   # min gap for on-demand (login/dashboard) syncs

    @field_validator("DEFAULT_AI_PROVIDER", mode="before")
    @classmethod
    def _normalize_default_ai_provider(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("IDEMPOTENCY_BACKEND", mode="before")
    @classmethod
    def _normalize_idempotency_backend(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("APP_MODE", mode="before")
    @classmethod
    def _normalize_app_mode(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @property
    def app_mode_normalized(self) -> str:
        return self.APP_MODE


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
    idem_backend = s.IDEMPOTENCY_BACKEND
    if idem_backend == "redis" and not (s.IDEMPOTENCY_REDIS_URL or "").strip():
        issues.append("IDEMPOTENCY_REDIS_URL must be set when IDEMPOTENCY_BACKEND=redis")
    if s.IDEMPOTENCY_TTL_SECONDS < 60:
        issues.append("IDEMPOTENCY_TTL_SECONDS must be >= 60")
    if s.IDEMPOTENCY_MAX_ITEMS < 100:
        issues.append("IDEMPOTENCY_MAX_ITEMS must be >= 100")

    provider = s.DEFAULT_AI_PROVIDER
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
    if s.PRIVACY_AUDIT_MAX_VALUE_CHARS < 32:
        issues.append("PRIVACY_AUDIT_MAX_VALUE_CHARS must be >= 32")
    if s.WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS < 30:
        issues.append("WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS must be >= 30")
    if not s.DEBUG and not s.COOKIE_SECURE:
        issues.append("COOKIE_SECURE must be true when DEBUG=false (production mode)")
    token_key = (s.TOKEN_ENCRYPTION_KEY or "").strip()
    if not token_key:
        issues.append("TOKEN_ENCRYPTION_KEY should be set for key separation from SECRET_KEY")
    else:
        if token_key == s.SECRET_KEY:
            issues.append("TOKEN_ENCRYPTION_KEY must not equal SECRET_KEY")
        if len(token_key) < 32:
            issues.append("TOKEN_ENCRYPTION_KEY should be at least 32 characters")
    if s.WHATSAPP_WEBHOOK_VERIFY_TOKEN and not s.WHATSAPP_APP_SECRET:
        issues.append("WHATSAPP_APP_SECRET should be set when WhatsApp webhook verify token is configured")

    return issues
