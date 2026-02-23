from app.core.config import Settings, validate_startup_settings
from pydantic import ValidationError


def _base_settings(**overrides) -> Settings:
    data = {
        "DEFAULT_AI_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-live-valid-key-value",
        "DEBUG": False,
        "COOKIE_SECURE": True,
        "TOKEN_ENCRYPTION_KEY": "x" * 32,
        "SECRET_KEY": "y" * 64,
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
