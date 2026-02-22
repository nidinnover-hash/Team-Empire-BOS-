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
        "pool_size": 5,          # base pool size
        "max_overflow": 10,      # allow up to 15 connections under load
        "pool_recycle": 1800,    # recycle every 30 min to avoid idle-timeout drops
        "pool_timeout": 30,      # wait at most 30 s for a free connection
    })

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # objects stay readable after commit
)
