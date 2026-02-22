"""
Shared test fixtures.

Every test gets:
  - A fresh in-memory SQLite database (never touches personal_clone.db)
  - An async HTTP client wired to the FastAPI app
  - The get_db dependency overridden to use the test database
"""
import os

import pytest_asyncio

# Must be set before app is imported so the SECRET_KEY guard doesn't fire.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-tests-32c")
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.deps import get_db
from app.db.base import Base
from app.main import app as fastapi_app

# Register all models so Base.metadata knows about the tables
import app.models.command       # noqa: F401
import app.models.note          # noqa: F401
import app.models.task          # noqa: F401
import app.models.user          # noqa: F401
import app.models.organization  # noqa: F401
import app.models.approval      # noqa: F401
import app.models.execution     # noqa: F401
import app.models.event         # noqa: F401
import app.models.integration   # noqa: F401
import app.models.memory        # noqa: F401
import app.models.email         # noqa: F401
import app.models.daily_plan    # noqa: F401
import app.models.daily_run     # noqa: F401
import app.models.project       # noqa: F401
import app.models.goal          # noqa: F401
import app.models.contact       # noqa: F401
import app.models.finance       # noqa: F401

# StaticPool + check_same_thread=False makes all connections share one
# in-memory SQLite database — required for :memory: to work across requests.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables fresh for this test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    TestSession = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with TestSession() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Teardown: remove overrides and wipe the test database
    fastapi_app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
