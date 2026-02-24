from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# PostgreSQL gets a real connection pool; SQLite uses its default (StaticPool).
_engine_kwargs: dict = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,   # drops stale connections automatically
}
if not _is_sqlite:
    _engine_kwargs.update({
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": 1800,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
    })

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # objects stay readable after commit
)
