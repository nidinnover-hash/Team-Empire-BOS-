from app.core.config import Settings, format_startup_issues, validate_startup_settings
from pydantic import ValidationError


def _base_settings(**overrides) -> Settings:
    data = {
        "DEFAULT_AI_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-live-valid-key-value",
        "DEBUG": False,
        "COOKIE_SECURE": True,
        "TOKEN_ENCRYPTION_KEY": "x" * 32,
        "SECRET_KEY": "y" * 64,
        "ADMIN_PASSWORD": "StrongTestPass2026!",
        "WHATSAPP_WEBHOOK_REPLAY_WINDOW_SECONDS": 300,
        "WHATSAPP_WEBHOOK_VERIFY_TOKEN": None,
        "WHATSAPP_APP_SECRET": None,
    }
    data.update(overrides)
    return Settings(**data)


def test_validate_startup_flags_insecure_cookie_in_production():
    s = _base_settings(COOKIE_SECURE=False, DEBUG=False)
    issues = validate_startup_settings(s)
    assert any("COOKIE_SECURE" in i for i in issues)


def test_validate_startup_flags_missing_token_encryption_key():
    s = _base_settings(TOKEN_ENCRYPTION_KEY=None)
    issues = validate_startup_settings(s)
    assert any("TOKEN_ENCRYPTION_KEY should be set" in i for i in issues)


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


def test_validate_startup_flags_rate_limit_max_too_high():
    s = _base_settings(RATE_LIMIT_MAX_REQUESTS=50000)
    issues = validate_startup_settings(s)
    assert any("RATE_LIMIT_MAX_REQUESTS must be <= 10000" in i for i in issues)


def test_validate_startup_clean_passes():
    s = _base_settings()
    issues = validate_startup_settings(s)
    assert issues == []


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
