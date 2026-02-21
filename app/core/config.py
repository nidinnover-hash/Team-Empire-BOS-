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
    DATABASE_URL: str = "sqlite+aiosqlite:///./personal_clone.db"

    # ── OpenAI (used later when we wire in the AI call) ───────────────────────
    OPENAI_API_KEY: str | None = None

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Personal Clone"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
