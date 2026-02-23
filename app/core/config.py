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
RateLimitBackend = Literal["auto", "memory", "redis"]
PrivacyPolicyProfile = Literal["strict", "balanced", "debug"]


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
    RATE_LIMIT_BACKEND: RateLimitBackend = "auto"
    RATE_LIMIT_REDIS_URL: str | None = None
    RATE_LIMIT_REDIS_PREFIX: str = "pc:ratelimit"
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
    PRIVACY_POLICY_PROFILE: PrivacyPolicyProfile = "balanced"
    PRIVACY_AUDIT_MAX_VALUE_CHARS: int = 200
    CLONE_AUTO_LEARN_FROM_CHAT: bool = True

    # Ops Intelligence guardrails
    WORK_EMAIL_DOMAINS: str = ""  # Comma-separated: "empire.com,empireo.ai"
    GMAIL_LABEL_ALLOWLIST: str = ""  # Comma-separated: "INBOX,work"

    # Background sync scheduler
    SYNC_ENABLED: bool = True
    SYNC_INTERVAL_MINUTES: int = 30   # how often the scheduler fires
    SYNC_THROTTLE_MINUTES: int = 15   # min gap for on-demand (login/dashboard) syncs

    @field_validator(
        "DEFAULT_AI_PROVIDER", "IDEMPOTENCY_BACKEND", "RATE_LIMIT_BACKEND", "PRIVACY_POLICY_PROFILE",
        mode="before",
    )
    @classmethod
    def _normalize_lowercase(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("APP_MODE", mode="before")
    @classmethod
    def _normalize_uppercase(cls, value: Any) -> Any:
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

    # --- Numeric bounds ---
    if s.ACCESS_TOKEN_EXPIRE_MINUTES < 5:
        issues.append("ACCESS_TOKEN_EXPIRE_MINUTES must be >= 5")
    if s.ACCESS_TOKEN_EXPIRE_MINUTES > 40_320:  # 28 days
        issues.append("ACCESS_TOKEN_EXPIRE_MINUTES must be <= 40320 (28 days)")
    if s.SYNC_INTERVAL_MINUTES < 1:
        issues.append("SYNC_INTERVAL_MINUTES must be >= 1")
    if s.SYNC_INTERVAL_MINUTES > 1_440:  # 24 hours
        issues.append("SYNC_INTERVAL_MINUTES must be <= 1440 (24 hours)")
    if s.SYNC_THROTTLE_MINUTES < 0:
        issues.append("SYNC_THROTTLE_MINUTES must be >= 0")

    # --- Rate limiting / idempotency ---
    idem_backend = s.IDEMPOTENCY_BACKEND
    if idem_backend == "redis" and not (s.IDEMPOTENCY_REDIS_URL or "").strip():
        issues.append("IDEMPOTENCY_REDIS_URL must be set when IDEMPOTENCY_BACKEND=redis")
    if s.IDEMPOTENCY_TTL_SECONDS < 60:
        issues.append("IDEMPOTENCY_TTL_SECONDS must be >= 60")
    if s.IDEMPOTENCY_TTL_SECONDS > 86_400:  # 24 hours
        issues.append("IDEMPOTENCY_TTL_SECONDS must be <= 86400 (24 hours)")
    if s.IDEMPOTENCY_MAX_ITEMS < 100:
        issues.append("IDEMPOTENCY_MAX_ITEMS must be >= 100")
    if s.RATE_LIMIT_BACKEND == "redis" and not (s.RATE_LIMIT_REDIS_URL or "").strip():
        issues.append("RATE_LIMIT_REDIS_URL must be set when RATE_LIMIT_BACKEND=redis")
    if s.RATE_LIMIT_WINDOW_SECONDS < 1:
        issues.append("RATE_LIMIT_WINDOW_SECONDS must be >= 1")
    if s.RATE_LIMIT_MAX_REQUESTS < 1:
        issues.append("RATE_LIMIT_MAX_REQUESTS must be >= 1")
    if s.RATE_LIMIT_MAX_REQUESTS > 10_000:
        issues.append("RATE_LIMIT_MAX_REQUESTS must be <= 10000")

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
    if not s.DEBUG and s.PRIVACY_POLICY_PROFILE == "debug":
        issues.append("PRIVACY_POLICY_PROFILE=debug is not allowed when DEBUG=false")

    # --- Security: reject insecure defaults ---
    _WEAK_SECRETS = {"change_me_in_env", "secret", "changeme", "your_32_plus_char_secret_here"}
    if s.SECRET_KEY in _WEAK_SECRETS or len(s.SECRET_KEY) < 16:
        issues.append("SECRET_KEY is a placeholder or too short (min 16 chars)")
    _WEAK_PASSWORDS = {"demo", "password", "admin", "123456", "changeme"}
    if s.ADMIN_PASSWORD in _WEAK_PASSWORDS or len(s.ADMIN_PASSWORD) < 8:
        issues.append("ADMIN_PASSWORD is weak or too short (min 8 chars)")

    return issues


def format_startup_issues(issues: list[str]) -> str:
    groups: dict[str, list[str]] = {
        "security": [],
        "integrations": [],
        "runtime": [],
    }
    for issue in issues:
        upper = issue.upper()
        if any(k in upper for k in {"SECRET", "COOKIE", "TOKEN_ENCRYPTION_KEY", "WHATSAPP_APP_SECRET", "ADMIN_PASSWORD"}):
            groups["security"].append(issue)
        elif any(k in upper for k in {"OPENAI", "ANTHROPIC", "GROQ", "GOOGLE", "WHATSAPP"}):
            groups["integrations"].append(issue)
        else:
            groups["runtime"].append(issue)

    lines: list[str] = []
    for name in ("security", "integrations", "runtime"):
        items = groups[name]
        if not items:
            continue
        lines.append(f"{name}:")
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)
