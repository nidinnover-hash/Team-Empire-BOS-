from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # silently drop any unrecognised env vars
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/personal_clone"

    # ── OpenAI (used later when we wire in the AI call) ───────────────────────
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    DEFAULT_AI_PROVIDER: str = "openai"
    AGENT_MODEL_OPENAI: str = "gpt-4o-mini"
    AGENT_MODEL_ANTHROPIC: str = "claude-haiku-4-5-20251001"
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Personal Clone"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    AUTO_CREATE_SCHEMA: bool = False
    AUTO_SEED_DEFAULTS: bool = False
    SECRET_KEY: str = "change_me_in_env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
