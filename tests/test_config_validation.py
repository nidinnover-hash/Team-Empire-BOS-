from app.core.config import Settings, format_startup_issues, validate_startup_settings
from pydantic import ValidationError


def _base_settings(**overrides) -> Settings:
    data = {
        "DEFAULT_AI_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-live-valid-key-value",
        "GOOGLE_CLIENT_ID": None,
        "GOOGLE_CLIENT_SECRET": None,
        "GOOGLE_REDIRECT_URI": None,
        "DEBUG": False,
        "COOKIE_SECURE": True,
        "PRIVACY_POLICY_PROFILE": "strict",
        "TOKEN_ENCRYPTION_KEY": "x" * 32,
        "SECRET_KEY": "y" * 64,
        "ADMIN_PASSWORD": "StrongTestPass2026!",
        "ACCESS_TOKEN_EXPIRE_MINUTES": 60,
        "WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS": 300,
        "WHATSAPP_WEBHOOK_VERIFY_TOKEN": None,
        "WHATSAPP_APP_SECRET": None,
        "SECURITY_PREMIUM_MODE": True,
        "LEGAL_TERMS_VERSION": "2026-02-24",
        "LEGAL_DPA_REQUIRED": True,
        "ACCOUNT_MFA_REQUIRED": True,
        "ACCOUNT_SESSION_MAX_HOURS": 12,
        "AUTO_CREATE_SCHEMA": False,
        "AUTO_SEED_DEFAULTS": False,
        "MARKETING_EXPORT_PII_ALLOWED": False,
        "PURPOSE_PERSONAL_EMAILS": "nidinnover@gmail.com",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/personal_clone_test",
    }
    data.update(overrides)
    return Settings(**data)


def test_validate_startup_flags_insecure_cookie_in_production():
    s = _base_settings(COOKIE_SECURE=False, DEBUG=False)
    issues = validate_startup_settings(s)
    assert any("COOKIE_SECURE" in i for i in issues)


def test_validate_startup_rejects_sqlite_in_production_mode():
    s = _base_settings(DEBUG=False, DATABASE_URL="sqlite:///./prod.db")
    issues = validate_startup_settings(s)
    assert any("should not use sqlite when DEBUG=false" in i for i in issues)


def test_validate_startup_rejects_auto_create_schema_in_production_mode():
    s = _base_settings(DEBUG=False, AUTO_CREATE_SCHEMA=True)
    issues = validate_startup_settings(s)
    assert any("AUTO_CREATE_SCHEMA must be false when DEBUG=false" in i for i in issues)


def test_validate_startup_rejects_auto_seed_defaults_in_production_mode():
    s = _base_settings(DEBUG=False, AUTO_SEED_DEFAULTS=True)
    issues = validate_startup_settings(s)
    assert any("AUTO_SEED_DEFAULTS must be false when DEBUG=false" in i for i in issues)


def test_validate_startup_flags_missing_token_encryption_key():
    s = _base_settings(TOKEN_ENCRYPTION_KEY=None)
    issues = validate_startup_settings(s)
    assert any("TOKEN_ENCRYPTION_KEY must be set" in i for i in issues)


def test_validate_startup_flags_same_token_and_secret_key():
    s = _base_settings(TOKEN_ENCRYPTION_KEY="z" * 64, SECRET_KEY="z" * 64)
    issues = validate_startup_settings(s)
    assert any("must not equal SECRET_KEY" in i for i in issues)


def test_validate_startup_flags_short_replay_window():
    s = _base_settings(WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS=10)
    issues = validate_startup_settings(s)
    assert any("WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS" in i for i in issues)


def test_validate_startup_flags_missing_whatsapp_app_secret():
    s = _base_settings(WHATSAPP_WEBHOOK_VERIFY_TOKEN="verify-me", WHATSAPP_APP_SECRET=None)
    issues = validate_startup_settings(s)
    assert any("WHATSAPP_APP_SECRET" in i for i in issues)


def test_validate_startup_accepts_case_insensitive_app_mode():
    s = _base_settings(APP_MODE=" empireo_ai ")
    issues = validate_startup_settings(s)
    assert not any("APP_MODE has unsupported value" in i for i in issues)


def test_validate_startup_flags_redis_without_url():
    s = _base_settings(IDEMPOTENCY_BACKEND="redis", IDEMPOTENCY_REDIS_URL=None)
    issues = validate_startup_settings(s)
    assert any("IDEMPOTENCY_REDIS_URL" in i for i in issues)


def test_validate_startup_flags_rate_limit_redis_without_url():
    s = _base_settings(RATE_LIMIT_BACKEND="redis", RATE_LIMIT_REDIS_URL=None)
    issues = validate_startup_settings(s)
    assert any("RATE_LIMIT_REDIS_URL" in i for i in issues)


def test_settings_normalize_provider_and_backend_and_mode():
    s = _base_settings(
        DEFAULT_AI_PROVIDER=" AnThRoPiC ",
        IDEMPOTENCY_BACKEND=" ReDiS ",
        IDEMPOTENCY_REDIS_URL="redis://localhost:6379/0",
        APP_MODE=" nidin_ai ",
    )
    assert s.DEFAULT_AI_PROVIDER == "anthropic"
    assert s.IDEMPOTENCY_BACKEND == "redis"
    assert s.APP_MODE == "NIDIN_AI"


def test_settings_reject_invalid_idempotency_backend():
    try:
        _base_settings(IDEMPOTENCY_BACKEND="cachebox")
        raise AssertionError("Expected Settings validation to fail")
    except ValidationError as exc:
        assert "IDEMPOTENCY_BACKEND" in str(exc)


def test_validate_startup_flags_weak_secret_key():
    s = _base_settings(SECRET_KEY="change_me_in_env")
    issues = validate_startup_settings(s)
    assert any("SECRET_KEY" in i and "placeholder" in i for i in issues)


def test_validate_startup_flags_short_secret_key():
    s = _base_settings(SECRET_KEY="tooshort")
    issues = validate_startup_settings(s)
    assert any("SECRET_KEY" in i for i in issues)


def test_validate_startup_flags_weak_admin_password():
    s = _base_settings(ADMIN_PASSWORD="demo")
    issues = validate_startup_settings(s)
    assert any("ADMIN_PASSWORD" in i for i in issues)


def test_validate_startup_flags_short_admin_password():
    s = _base_settings(ADMIN_PASSWORD="abc")
    issues = validate_startup_settings(s)
    assert any("ADMIN_PASSWORD" in i for i in issues)


def test_validate_startup_flags_token_expire_too_low():
    s = _base_settings(ACCESS_TOKEN_EXPIRE_MINUTES=2)
    issues = validate_startup_settings(s)
    assert any("ACCESS_TOKEN_EXPIRE_MINUTES must be >= 5" in i for i in issues)


def test_validate_startup_flags_token_expire_too_high():
    s = _base_settings(ACCESS_TOKEN_EXPIRE_MINUTES=99999)
    issues = validate_startup_settings(s)
    assert any("ACCESS_TOKEN_EXPIRE_MINUTES must be <= 40320" in i for i in issues)


def test_validate_startup_flags_sync_interval_bounds():
    s = _base_settings(SYNC_INTERVAL_MINUTES=0)
    issues = validate_startup_settings(s)
    assert any("SYNC_INTERVAL_MINUTES must be >= 1" in i for i in issues)


def test_validate_startup_flags_sync_failure_alert_threshold_bounds():
    low = _base_settings(SYNC_FAILURE_ALERT_THRESHOLD=0)
    high = _base_settings(SYNC_FAILURE_ALERT_THRESHOLD=101)
    low_issues = validate_startup_settings(low)
    high_issues = validate_startup_settings(high)
    assert any("SYNC_FAILURE_ALERT_THRESHOLD must be >= 1" in i for i in low_issues)
    assert any("SYNC_FAILURE_ALERT_THRESHOLD must be <= 100" in i for i in high_issues)


def test_validate_startup_flags_memory_context_cache_bounds():
    low_ttl = _base_settings(MEMORY_CONTEXT_CACHE_TTL_SECONDS=10)
    high_ttl = _base_settings(MEMORY_CONTEXT_CACHE_TTL_SECONDS=90_000)
    low_orgs = _base_settings(MEMORY_CONTEXT_CACHE_MAX_ORGS=5)
    high_orgs = _base_settings(MEMORY_CONTEXT_CACHE_MAX_ORGS=20_000)
    assert any(
        "MEMORY_CONTEXT_CACHE_TTL_SECONDS must be >= 30" in i
        for i in validate_startup_settings(low_ttl)
    )
    assert any(
        "MEMORY_CONTEXT_CACHE_TTL_SECONDS must be <= 86400" in i
        for i in validate_startup_settings(high_ttl)
    )
    assert any(
        "MEMORY_CONTEXT_CACHE_MAX_ORGS must be >= 10" in i
        for i in validate_startup_settings(low_orgs)
    )
    assert any(
        "MEMORY_CONTEXT_CACHE_MAX_ORGS must be <= 10000" in i
        for i in validate_startup_settings(high_orgs)
    )


def test_validate_startup_flags_rate_limit_max_too_high():
    s = _base_settings(RATE_LIMIT_MAX_REQUESTS=50000)
    issues = validate_startup_settings(s)
    assert any("RATE_LIMIT_MAX_REQUESTS must be <= 10000" in i for i in issues)


def test_validate_startup_flags_missing_email_provider_key_when_overridden():
    s = _base_settings(
        DEFAULT_AI_PROVIDER="openai",
        OPENAI_API_KEY="sk-live-valid-key-value",
        EMAIL_AI_PROVIDER="anthropic",
        ANTHROPIC_API_KEY=None,
    )
    issues = validate_startup_settings(s)
    assert any("EMAIL_AI_PROVIDER=anthropic" in i for i in issues)


def test_validate_startup_flags_invalid_cors_wildcard():
    s = _base_settings(CORS_ALLOWED_ORIGINS="*")
    issues = validate_startup_settings(s)
    assert any("must not include '*'" in i for i in issues)


def test_validate_startup_flags_invalid_cors_path():
    s = _base_settings(CORS_ALLOWED_ORIGINS="https://app.example.com/path")
    issues = validate_startup_settings(s)
    assert any("must not include a path" in i for i in issues)


def test_validate_startup_flags_http_cors_origin_in_production():
    s = _base_settings(DEBUG=False, CORS_ALLOWED_ORIGINS="http://example.com")
    issues = validate_startup_settings(s)
    assert any("must use https in production" in i for i in issues)


def test_validate_startup_flags_web_api_token_ttl_bounds():
    low = _base_settings(WEB_API_TOKEN_EXPIRE_MINUTES=0)
    high = _base_settings(WEB_API_TOKEN_EXPIRE_MINUTES=121)
    low_issues = validate_startup_settings(low)
    high_issues = validate_startup_settings(high)
    assert any("WEB_API_TOKEN_EXPIRE_MINUTES must be between 1 and 120" in i for i in low_issues)
    assert any("WEB_API_TOKEN_EXPIRE_MINUTES must be between 1 and 120" in i for i in high_issues)


def test_validate_startup_flags_unknown_env_keys(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/personal_clone_test\n"
        "UNKNOWN_CONFIG_FLAG=true\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(Settings.model_config, "env_file", str(env_file))

    s = _base_settings(DEBUG=False)
    issues = validate_startup_settings(s)
    assert any("UNKNOWN_CONFIG_FLAG" in i for i in issues)


def test_validate_startup_clean_passes():
    s = _base_settings()
    issues = validate_startup_settings(s)
    assert issues == []


def test_validate_startup_rejects_debug_privacy_profile_in_production():
    s = _base_settings(DEBUG=False, PRIVACY_POLICY_PROFILE="debug")
    issues = validate_startup_settings(s)
    assert any("PRIVACY_POLICY_PROFILE=debug is not allowed" in i for i in issues)


def test_validate_startup_premium_requires_strict_privacy_profile():
    s = _base_settings(PRIVACY_POLICY_PROFILE="balanced")
    issues = validate_startup_settings(s)
    assert any("must be strict when SECURITY_PREMIUM_MODE=true" in i for i in issues)


def test_validate_startup_premium_rejects_marketing_pii_export():
    s = _base_settings(MARKETING_EXPORT_PII_ALLOWED=True)
    issues = validate_startup_settings(s)
    assert any("MARKETING_EXPORT_PII_ALLOWED must be false" in i for i in issues)


def test_validate_startup_account_session_hours_bounds():
    s = _base_settings(ACCOUNT_SESSION_MAX_HOURS=48)
    issues = validate_startup_settings(s)
    assert any("ACCOUNT_SESSION_MAX_HOURS must be between 1 and 24" in i for i in issues)


def test_validate_startup_flags_missing_purpose_email_lists_with_strict_barriers():
    s = _base_settings(PURPOSE_PERSONAL_EMAILS="", PURPOSE_ENTERTAINMENT_EMAILS="")
    issues = validate_startup_settings(s)
    assert any("PURPOSE_STRICT_BARRIERS=true but no purpose emails configured" in i for i in issues)


def test_validate_startup_flags_overlapping_purpose_email_lists():
    s = _base_settings(
        PURPOSE_PERSONAL_EMAILS="user@example.com",
        PURPOSE_ENTERTAINMENT_EMAILS="user@example.com",
    )
    issues = validate_startup_settings(s)
    assert any("must not overlap" in i for i in issues)


def test_validate_startup_flags_invalid_purpose_email_values():
    s = _base_settings(
        PURPOSE_PERSONAL_EMAILS="invalid-email",
        PURPOSE_ENTERTAINMENT_EMAILS="",
    )
    issues = validate_startup_settings(s)
    assert any("invalid email values" in i for i in issues)


def test_format_startup_issues_groups_by_domain():
    text = format_startup_issues(
        [
            "COOKIE_SECURE must be true when DEBUG=false (production mode)",
            "OPENAI_API_KEY is missing or placeholder while DEFAULT_AI_PROVIDER=openai",
            "RATE_LIMIT_MAX_REQUESTS must be >= 1",
        ]
    )
    assert "security:" in text
    assert "integrations:" in text
    assert "runtime:" in text
