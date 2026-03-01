from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_OPENAI_KEYS = {"", "sk-your-key-here", "sk-xxxxxxxxxxxxxxxxxxxxxxxx"}
PLACEHOLDER_ANTHROPIC_KEYS = {"", "your-anthropic-key-here"}
PLACEHOLDER_GROQ_KEYS = {"", "gsk_your-key-here", "gsk_your_groq_key_here"}
PLACEHOLDER_GEMINI_KEYS = {"", "your-gemini-key-here"}
PLACEHOLDER_AI_KEYS = PLACEHOLDER_OPENAI_KEYS | PLACEHOLDER_ANTHROPIC_KEYS | PLACEHOLDER_GROQ_KEYS | PLACEHOLDER_GEMINI_KEYS
_PLACEHOLDER_GOOGLE_VALUES = {"", "replace-me", "your-google-client-id", "your-google-client-secret"}
AIProvider = Literal["openai", "anthropic", "groq", "gemini"]
IdempotencyBackend = Literal["auto", "memory", "redis"]
AppMode = Literal["NIDIN_AI", "EMPIREO_AI"]
RateLimitBackend = Literal["auto", "memory", "redis"]
PrivacyPolicyProfile = Literal["strict", "balanced", "debug"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",  # silently drop any unrecognized env vars
    )

    # Database
    DATABASE_URL: str = ""  # Must be set in .env

    # AI providers
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    DEFAULT_AI_PROVIDER: AIProvider = "openai"
    EMAIL_AI_PROVIDER: AIProvider | None = None  # Override AI provider for email; falls back to DEFAULT_AI_PROVIDER
    AGENT_MODEL_OPENAI: str = "gpt-4o-mini"
    AGENT_MODEL_ANTHROPIC: str = "claude-haiku-4-5-20251001"
    AGENT_MODEL_GROQ: str = "llama-3.3-70b-versatile"
    AGENT_MODEL_GEMINI: str = "gemini-2.0-flash"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    GOOGLE_CALENDAR_REDIRECT_URI: str | None = None  # Separate callback for Calendar OAuth
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str | None = None
    GITHUB_APP_ID: str | None = None
    GITHUB_PRIVATE_KEY_PEM: str | None = None
    GITHUB_ORG: str | None = None
    CRITICAL_GITHUB_REPOS: str = ""
    # Governance team members (comma-separated GitHub usernames)
    GITHUB_TECH_LEADS: str = ""
    GITHUB_DEVELOPERS: str = ""
    # Compliance engine company emails (comma-separated)
    COMPLIANCE_OWNER_EMAILS: str = "owner@example.com"
    COMPLIANCE_TECH_LEAD_EMAIL: str = ""
    COMPLIANCE_OPS_MANAGER_EMAIL: str = ""
    COMPLIANCE_DEV_EMAILS: str = ""
    COMPLIANCE_COMPANY_DOMAIN: str = "example.com"
    # Optional exceptions for personal identities (comma-separated emails).
    # Keep empty for strict company-only mode.
    COMPLIANCE_ALLOWED_PERSONAL_EMAILS: str = ""
    # If true, emails in COMPLIANCE_ALLOWED_PERSONAL_EMAILS can hold owner roles.
    COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS: bool = False
    PERSONAL_ORG_ID: int | None = None
    CLICKUP_CRITICAL_FOLDER_NAME: str = "🔴 Critical Systems"
    CLICKUP_CEO_PRIORITY_TAG: str = "CEO-PRIORITY"
    DIGITALOCEAN_BASE_URL: str = "https://api.digitalocean.com/v2"

    # New integrations
    PERPLEXITY_API_KEY: str | None = None
    LINKEDIN_CLIENT_ID: str | None = None
    LINKEDIN_CLIENT_SECRET: str | None = None
    LINKEDIN_REDIRECT_URI: str | None = None
    NOTION_API_KEY: str | None = None
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    GA4_PROPERTY_ID: str | None = None
    CALENDLY_API_KEY: str | None = None
    ELEVENLABS_API_KEY: str | None = None
    ELEVENLABS_DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    HUBSPOT_ACCESS_TOKEN: str | None = None

    # Internal API and rate limiting
    WHATSAPP_APP_SECRET: str | None = None   # Used to verify X-Hub-Signature-256 on webhook POSTs
    WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS: int = 60
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
    APP_NAME: str = "Nidin BOS"
    APP_MODE: AppMode = "NIDIN_AI"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENFORCE_STARTUP_VALIDATION: bool = False
    AUTO_CREATE_SCHEMA: bool = False
    AUTO_SEED_DEFAULTS: bool = False
    COOKIE_SECURE: bool = False  # Set True in production (requires HTTPS)
    SECRET_KEY: str = ""  # Must be set in .env (min 32 chars)
    ADMIN_EMAIL: str = "demo@ai.com"
    ADMIN_PASSWORD: str = ""  # Must be set in .env (min 8 chars)
    ADMIN_NAME: str = "Nidin Nover"
    ALGORITHM: Literal["HS256"] = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CHAT_HISTORY_RETENTION_DAYS: int = 90
    # Separate key for Fernet token encryption (Integration.config_json).
    # This should always be set and must differ from SECRET_KEY.
    TOKEN_ENCRYPTION_KEY: str | None = None
    # Separate key for OAuth state HMAC signing.
    # Falls back to SECRET_KEY if not set — set a distinct value to avoid key coupling.
    OAUTH_STATE_KEY: str | None = None
    PRIVACY_REDACTION_ENABLED: bool = True
    PRIVACY_MASK_PII: bool = True
    PRIVACY_RESPONSE_SANITIZATION_ENABLED: bool = True
    PRIVACY_POLICY_PROFILE: PrivacyPolicyProfile = "strict"
    PRIVACY_AUDIT_MAX_VALUE_CHARS: int = 200
    CLONE_AUTO_LEARN_FROM_CHAT: bool = True
    SECURITY_PREMIUM_MODE: bool = True
    LEGAL_TERMS_VERSION: str = "2026-02-24"
    LEGAL_DPA_REQUIRED: bool = True
    LEGAL_MARKETING_CONSENT_REQUIRED: bool = True
    ACCOUNT_SSO_REQUIRED: bool = False
    ACCOUNT_MFA_REQUIRED: bool = True
    ACCOUNT_SESSION_MAX_HOURS: int = 12
    MARKETING_EXPORT_PII_ALLOWED: bool = False

    # CORS
    CORS_ALLOWED_ORIGINS: str = ""  # Comma-separated, e.g. "http://localhost:8002,https://app.nidin.ai"

    # Ops Intelligence guardrails
    WORK_EMAIL_DOMAINS: str = ""  # Comma-separated: "empire.com,empireo.ai"
    GMAIL_LABEL_ALLOWLIST: str = ""  # Comma-separated: "INBOX,work"

    # Global request body size limit (bytes). 0 = unlimited.
    MAX_REQUEST_BODY_BYTES: int = 10 * 1024 * 1024  # 10 MB

    # Database connection pool (PostgreSQL only; ignored for SQLite)
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # Compose rate limiting
    COMPOSE_MAX_PER_HOUR: int = 20
    COMPOSE_WINDOW_SECONDS: int = 3600
    EMAIL_CONTROL_REPORT_SUBJECT_PREFIX: str = "[REPORT]"
    EMAIL_CONTROL_DIGEST_ENABLED: bool = True
    EMAIL_CONTROL_DIGEST_TO: str | None = None
    EMAIL_CONTROL_DIGEST_HOUR_IST: int = 18
    EMAIL_CONTROL_DIGEST_MINUTE_IST: int = 0
    MANAGER_REPORT_CUTOFF_HOUR_IST: int = 19
    APPROVAL_SLA_HOURS: int = 24

    # Background sync scheduler
    RUN_SCHEDULER: bool = False  # Set via env; avoids os.environ.get() bypass
    SYNC_ENABLED: bool = True
    SYNC_INTERVAL_MINUTES: int = 30   # how often the scheduler fires
    SYNC_THROTTLE_MINUTES: int = 15   # min gap for on-demand (login/dashboard) syncs
    SHUTDOWN_GRACE_SECONDS: int = 15  # max wait for in-flight syncs on shutdown
    LOG_FORMAT: Literal["json", "text"] = "text"
    LOG_LEVEL: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    # Use forwarded headers only when running behind a trusted reverse proxy.
    USE_FORWARDED_HEADERS: bool = False
    # Comma-separated CIDRs of trusted reverse proxies.
    TRUSTED_PROXY_CIDRS: str = ""
    # Short-lived API token minted from web session for browser-side API calls.
    WEB_API_TOKEN_EXPIRE_MINUTES: int = 15
    CEO_SUMMARY_TIMEZONE: str = "Asia/Kolkata"
    CEO_ALERTS_SLACK_CHANNEL_ID: str | None = None
    SYNC_STALE_HOURS: int = 24
    SYNC_FAILURE_ALERT_THRESHOLD: int = 3
    MEMORY_CONTEXT_CACHE_TTL_SECONDS: int = 300
    MEMORY_CONTEXT_CACHE_MAX_ORGS: int = 200

    # Tunable timeouts and limits
    AI_TIMEOUT_SECONDS: float = 20.0       # per-request timeout for AI provider calls
    AI_RETRY_ATTEMPTS: int = 2             # total attempts per provider call (includes first try)
    AI_RETRY_BACKOFF_SECONDS: float = 1.5  # exponential backoff base between retries
    AI_RETRY_MAX_BACKOFF_SECONDS: float = 8.0
    EXPORT_MAX_ROWS: int = 2000            # max rows per table in full data export
    BACKUP_TIMEOUT_SECONDS: int = 300      # pg_dump timeout for DB backup
    LOGIN_FAIL_WINDOW_SECONDS: int = 900   # sliding window for login failure tracking
    LOGIN_FAIL_MAX_ATTEMPTS: int = 10      # max failures before IP lockout

    # Optional OpenTelemetry tracing (set OTEL_EXPORTER_OTLP_ENDPOINT to activate)
    # Packages required: opentelemetry-api opentelemetry-sdk
    #   opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy
    #   opentelemetry-exporter-otlp-proto-http
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = "nidin-bos"

    # Feature flags — disable expensive features without redeploying
    FEATURE_AI_COMMANDS: bool = True     # AI responses in command input
    FEATURE_EMAIL_SYNC: bool = True      # Gmail sync + email AI
    FEATURE_TALK_MODE: bool = True       # Voice/chat Talk Mode page
    FEATURE_OPS_INTEL: bool = True       # Ops Intelligence page
    FEATURE_DAILY_RUN: bool = True       # Daily run draft generation
    CLONE_REQUIRE_CLARIFYING_QUESTION: bool = True
    CLONE_PATTERN_AUTOMATION_ENABLED: bool = False
    CLONE_PATTERN_WINDOW: int = 50
    CLONE_UNUSUAL_ACTIVITY_ALERTS: bool = True
    PURPOSE_PERSONAL_EMAILS: str = ""
    PURPOSE_ENTERTAINMENT_EMAILS: str = ""
    PURPOSE_DEFAULT_THEME_PROFESSIONAL: Literal["light", "dark"] = "light"
    PURPOSE_DEFAULT_THEME_PERSONAL: Literal["light", "dark"] = "dark"
    PURPOSE_DEFAULT_THEME_ENTERTAINMENT: Literal["light", "dark"] = "dark"
    PURPOSE_STRICT_BARRIERS: bool = True

    @field_validator("EMAIL_AI_PROVIDER", mode="before")
    @classmethod
    def _empty_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return None
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator(
        "DEFAULT_AI_PROVIDER",
        "IDEMPOTENCY_BACKEND",
        "RATE_LIMIT_BACKEND",
        "PRIVACY_POLICY_PROFILE",
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

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @property
    def app_mode_normalized(self) -> str:
        return self.APP_MODE

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()


def _settings_env_file_paths() -> list[Path]:
    raw = Settings.model_config.get("env_file")
    if raw is None:
        return []
    values = raw if isinstance(raw, list | tuple) else [raw]
    paths: list[Path] = []
    for value in values:
        path = Path(str(value))
        paths.append(path)
    return paths


def _parse_env_keys_from_file(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key and key.replace("_", "").isalnum() and not key[0].isdigit():
            keys.add(key)
    return keys


def _unknown_env_file_keys() -> list[str]:
    known = set(Settings.model_fields.keys())
    unknown: set[str] = set()
    for path in _settings_env_file_paths():
        unknown.update(_parse_env_keys_from_file(path) - known)
    return sorted(unknown)


def validate_startup_settings(s: Settings) -> list[str]:
    """
    Return startup configuration issues.
    Enforcement is opt-in via ENFORCE_STARTUP_VALIDATION.
    """
    issues: list[str] = []
    admin_email = (s.ADMIN_EMAIL or "").strip().lower()
    if not admin_email or "@" not in admin_email:
        issues.append("ADMIN_EMAIL must be a valid email address")
    unknown_env = _unknown_env_file_keys()
    if unknown_env:
        issues.append("Unknown .env keys detected (possible typos): " + ", ".join(unknown_env))
    if not s.DEBUG and admin_email in {"demo@ai.com", "demo@local.ai"}:
        issues.append("ADMIN_EMAIL must not use demo addresses when DEBUG=false (production mode)")

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
    if s.SYNC_STALE_HOURS < 1:
        issues.append("SYNC_STALE_HOURS must be >= 1")
    if s.SYNC_STALE_HOURS > 168:
        issues.append("SYNC_STALE_HOURS must be <= 168 (7 days)")
    if s.SYNC_FAILURE_ALERT_THRESHOLD < 1:
        issues.append("SYNC_FAILURE_ALERT_THRESHOLD must be >= 1")
    if s.SYNC_FAILURE_ALERT_THRESHOLD > 100:
        issues.append("SYNC_FAILURE_ALERT_THRESHOLD must be <= 100")
    if s.MEMORY_CONTEXT_CACHE_TTL_SECONDS < 30:
        issues.append("MEMORY_CONTEXT_CACHE_TTL_SECONDS must be >= 30")
    if s.MEMORY_CONTEXT_CACHE_TTL_SECONDS > 86_400:
        issues.append("MEMORY_CONTEXT_CACHE_TTL_SECONDS must be <= 86400 (24 hours)")
    if s.MEMORY_CONTEXT_CACHE_MAX_ORGS < 10:
        issues.append("MEMORY_CONTEXT_CACHE_MAX_ORGS must be >= 10")
    if s.MEMORY_CONTEXT_CACHE_MAX_ORGS > 10_000:
        issues.append("MEMORY_CONTEXT_CACHE_MAX_ORGS must be <= 10000")
    if not (0 <= s.EMAIL_CONTROL_DIGEST_HOUR_IST <= 23):
        issues.append("EMAIL_CONTROL_DIGEST_HOUR_IST must be between 0 and 23")
    if not (0 <= s.EMAIL_CONTROL_DIGEST_MINUTE_IST <= 59):
        issues.append("EMAIL_CONTROL_DIGEST_MINUTE_IST must be between 0 and 59")
    if not (0 <= s.MANAGER_REPORT_CUTOFF_HOUR_IST <= 23):
        issues.append("MANAGER_REPORT_CUTOFF_HOUR_IST must be between 0 and 23")
    if s.APPROVAL_SLA_HOURS < 1:
        issues.append("APPROVAL_SLA_HOURS must be >= 1")
    if not (s.GITHUB_ORG or "").strip() and (s.GITHUB_APP_ID or s.GITHUB_PRIVATE_KEY_PEM):
        issues.append("GITHUB_ORG must be set when GitHub App auth is configured")
    owner_emails = [x.strip().lower() for x in (s.COMPLIANCE_OWNER_EMAILS or "").split(",") if x.strip()]
    if not owner_emails:
        issues.append("COMPLIANCE_OWNER_EMAILS must include at least one owner email")
    company_domain = (s.COMPLIANCE_COMPANY_DOMAIN or "").strip().lower()
    if company_domain:
        bad_owner_emails = [e for e in owner_emails if "@" not in e or not e.endswith(f"@{company_domain}")]
        if bad_owner_emails and not s.COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS:
            issues.append("COMPLIANCE_OWNER_EMAILS must match COMPLIANCE_COMPANY_DOMAIN unless personal owner exceptions are enabled")
    if s.COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS and not (s.COMPLIANCE_ALLOWED_PERSONAL_EMAILS or "").strip():
        issues.append("COMPLIANCE_ALLOWED_PERSONAL_EMAILS must be set when COMPLIANCE_ALLOW_PERSONAL_OWNER_EXCEPTIONS=true")

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

    def _check_provider_key(provider: str, source_name: str) -> None:
        if provider == "openai":
            key = (s.OPENAI_API_KEY or "").strip()
            if key in PLACEHOLDER_OPENAI_KEYS:
                issues.append(f"OPENAI_API_KEY is missing or placeholder while {source_name}=openai")
        elif provider == "anthropic":
            key = (s.ANTHROPIC_API_KEY or "").strip()
            if key in PLACEHOLDER_ANTHROPIC_KEYS:
                issues.append(f"ANTHROPIC_API_KEY is missing or placeholder while {source_name}=anthropic")
        elif provider == "groq":
            key = (s.GROQ_API_KEY or "").strip()
            if key in PLACEHOLDER_GROQ_KEYS:
                issues.append(f"GROQ_API_KEY is missing or placeholder while {source_name}=groq")
        elif provider == "gemini":
            key = (s.GEMINI_API_KEY or "").strip()
            if key in PLACEHOLDER_GEMINI_KEYS:
                issues.append(f"GEMINI_API_KEY is missing or placeholder while {source_name}=gemini")

    provider = s.DEFAULT_AI_PROVIDER
    _check_provider_key(provider, "DEFAULT_AI_PROVIDER")
    email_provider = (s.EMAIL_AI_PROVIDER or provider)
    if email_provider != provider:
        _check_provider_key(email_provider, "EMAIL_AI_PROVIDER")
    google_id = (s.GOOGLE_CLIENT_ID or "").strip()
    google_secret = (s.GOOGLE_CLIENT_SECRET or "").strip()
    google_redirect = (s.GOOGLE_REDIRECT_URI or "").strip()
    any_google = bool(google_id or google_secret or google_redirect)
    all_google = bool(google_id and google_secret and google_redirect)

    if any_google and not all_google:
        issues.append("Google OAuth config is partial; set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI")
    if google_id and google_id in _PLACEHOLDER_GOOGLE_VALUES:
        issues.append("GOOGLE_CLIENT_ID looks like a placeholder")
    if google_secret and google_secret in _PLACEHOLDER_GOOGLE_VALUES:
        issues.append("GOOGLE_CLIENT_SECRET looks like a placeholder")
    if s.PRIVACY_AUDIT_MAX_VALUE_CHARS < 32:
        issues.append("PRIVACY_AUDIT_MAX_VALUE_CHARS must be >= 32")
    if s.WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS < 30:
        issues.append("WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS must be >= 30")
    if s.WEB_API_TOKEN_EXPIRE_MINUTES < 1 or s.WEB_API_TOKEN_EXPIRE_MINUTES > 120:
        issues.append("WEB_API_TOKEN_EXPIRE_MINUTES must be between 1 and 120")
    if s.AI_RETRY_ATTEMPTS < 1 or s.AI_RETRY_ATTEMPTS > 5:
        issues.append("AI_RETRY_ATTEMPTS must be between 1 and 5")
    if s.AI_RETRY_BACKOFF_SECONDS < 0 or s.AI_RETRY_BACKOFF_SECONDS > 30:
        issues.append("AI_RETRY_BACKOFF_SECONDS must be between 0 and 30")
    if s.AI_RETRY_MAX_BACKOFF_SECONDS < 0 or s.AI_RETRY_MAX_BACKOFF_SECONDS > 60:
        issues.append("AI_RETRY_MAX_BACKOFF_SECONDS must be between 0 and 60")
    if s.AI_RETRY_MAX_BACKOFF_SECONDS < s.AI_RETRY_BACKOFF_SECONDS:
        issues.append("AI_RETRY_MAX_BACKOFF_SECONDS must be >= AI_RETRY_BACKOFF_SECONDS")
    if not s.DEBUG and not s.COOKIE_SECURE:
        issues.append("COOKIE_SECURE must be true when DEBUG=false (production mode)")
    token_key = (s.TOKEN_ENCRYPTION_KEY or "").strip()
    if not token_key:
        issues.append("TOKEN_ENCRYPTION_KEY must be set for key separation from SECRET_KEY")
    else:
        if token_key == s.SECRET_KEY:
            issues.append("TOKEN_ENCRYPTION_KEY must not equal SECRET_KEY")
        if len(token_key) < 32:
            issues.append("TOKEN_ENCRYPTION_KEY should be at least 32 characters")
    if s.WHATSAPP_WEBHOOK_VERIFY_TOKEN and not s.WHATSAPP_APP_SECRET:
        issues.append("WHATSAPP_APP_SECRET should be set when WhatsApp webhook verify token is configured")
    if not s.DEBUG and s.PRIVACY_POLICY_PROFILE == "debug":
        issues.append("PRIVACY_POLICY_PROFILE=debug is not allowed when DEBUG=false")
    for origin in s.cors_allowed_origins_list:
        if origin == "*":
            issues.append("CORS_ALLOWED_ORIGINS must not include '*' when credentials are enabled")
            continue
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            issues.append(f"CORS origin is invalid: {origin!r}")
            continue
        if parsed.path not in {"", "/"}:
            issues.append(f"CORS origin must not include a path: {origin!r}")
            continue
        if not s.DEBUG and parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            issues.append(f"CORS origin must use https in production: {origin!r}")
    if s.ACCOUNT_SESSION_MAX_HOURS < 1 or s.ACCOUNT_SESSION_MAX_HOURS > 24:
        issues.append("ACCOUNT_SESSION_MAX_HOURS must be between 1 and 24")
    db_url = (s.DATABASE_URL or "").strip().lower()
    if not db_url:
        issues.append("DATABASE_URL must be configured")
    if not s.DEBUG and db_url.startswith("sqlite"):
        issues.append("DATABASE_URL should not use sqlite when DEBUG=false (production mode)")
    if not s.DEBUG and s.AUTO_CREATE_SCHEMA:
        issues.append("AUTO_CREATE_SCHEMA must be false when DEBUG=false (production mode)")
    if not s.DEBUG and s.AUTO_SEED_DEFAULTS:
        issues.append("AUTO_SEED_DEFAULTS must be false when DEBUG=false (production mode)")
    if s.SECURITY_PREMIUM_MODE:
        if s.PRIVACY_POLICY_PROFILE != "strict":
            issues.append("PRIVACY_POLICY_PROFILE must be strict when SECURITY_PREMIUM_MODE=true")
        if not s.ACCOUNT_MFA_REQUIRED:
            issues.append("ACCOUNT_MFA_REQUIRED must be true when SECURITY_PREMIUM_MODE=true")
        if not s.LEGAL_DPA_REQUIRED:
            issues.append("LEGAL_DPA_REQUIRED must be true when SECURITY_PREMIUM_MODE=true")
        if not (s.LEGAL_TERMS_VERSION or "").strip():
            issues.append("LEGAL_TERMS_VERSION must be set when SECURITY_PREMIUM_MODE=true")
        if s.MARKETING_EXPORT_PII_ALLOWED:
            issues.append("MARKETING_EXPORT_PII_ALLOWED must be false when SECURITY_PREMIUM_MODE=true")
    if s.PURPOSE_STRICT_BARRIERS:
        personal_emails = [x.strip().lower() for x in (s.PURPOSE_PERSONAL_EMAILS or "").split(",") if x.strip()]
        entertainment_emails = [x.strip().lower() for x in (s.PURPOSE_ENTERTAINMENT_EMAILS or "").split(",") if x.strip()]
        if not personal_emails and not entertainment_emails:
            issues.append(
                "PURPOSE_STRICT_BARRIERS=true but no purpose emails configured; "
                "set PURPOSE_PERSONAL_EMAILS and/or PURPOSE_ENTERTAINMENT_EMAILS"
            )
        overlap = sorted(set(personal_emails).intersection(entertainment_emails))
        if overlap:
            issues.append(
                "PURPOSE_PERSONAL_EMAILS and PURPOSE_ENTERTAINMENT_EMAILS must not overlap: "
                + ", ".join(overlap)
            )
        malformed = [
            value for value in set(personal_emails + entertainment_emails)
            if "@" not in value or value.startswith("@") or value.endswith("@")
        ]
        if malformed:
            issues.append("Purpose email lists contain invalid email values: " + ", ".join(sorted(malformed)))

    # --- Security: reject insecure defaults ---
    _WEAK_SECRETS = {"change_me_in_env", "secret", "changeme", "your_32_plus_char_secret_here"}
    if s.SECRET_KEY in _WEAK_SECRETS or len(s.SECRET_KEY) < 32:
        issues.append("SECRET_KEY is a placeholder or too short (min 32 chars)")
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
