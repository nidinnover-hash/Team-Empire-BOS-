from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine() -> AsyncEngine:
    db_url = (settings.DATABASE_URL or "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is not configured. Set DATABASE_URL in your environment or .env.")

    is_sqlite = db_url.startswith("sqlite")
    # PostgreSQL gets a real connection pool; SQLite uses its default (StaticPool).
    engine_kwargs: dict[str, Any] = {
        "echo": False,  # Never echo SQL — prevents sensitive data leaks in logs
        "pool_pre_ping": True,  # drops stale connections automatically
    }
    if not is_sqlite:
        engine_kwargs.update(
            {
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
                "pool_recycle": 1800,
                "pool_timeout": settings.DB_POOL_TIMEOUT,
            }
        )
    try:
        return create_async_engine(db_url, **engine_kwargs)
    except Exception as exc:
        raise RuntimeError(f"Invalid DATABASE_URL configuration: {db_url!r}") from exc


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # objects stay readable after commit
        )
    return _session_factory


class _LazyEngineProxy:
    def __getattr__(self, name: str):
        return getattr(get_engine(), name)


class _LazySessionFactory:
    def __call__(self, *args, **kwargs):
        return get_session_factory()(*args, **kwargs)


engine = _LazyEngineProxy()
AsyncSessionLocal = _LazySessionFactory()
