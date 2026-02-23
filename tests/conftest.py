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
os.environ.setdefault("ADMIN_PASSWORD", "TestPassword2026!")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ["DEBUG"] = "true"
os.environ["ENFORCE_STARTUP_VALIDATION"] = "false"
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.deps import get_db
from app.core.security import create_access_token
from app.db.base import Base
from app.main import app as fastapi_app

# Register all models so Base.metadata knows about the tables
from app.models import approval as _model_approval  # noqa: F401
from app.models import command as _model_command  # noqa: F401
from app.models import conversation as _model_conversation  # noqa: F401
from app.models import contact as _model_contact  # noqa: F401
from app.models import daily_plan as _model_daily_plan  # noqa: F401
from app.models import daily_run as _model_daily_run  # noqa: F401
from app.models import decision_trace as _model_decision_trace  # noqa: F401
from app.models import email as _model_email  # noqa: F401
from app.models import event as _model_event  # noqa: F401
from app.models import execution as _model_execution  # noqa: F401
from app.models import finance as _model_finance  # noqa: F401
from app.models import goal as _model_goal  # noqa: F401
from app.models import integration as _model_integration  # noqa: F401
from app.models import memory as _model_memory  # noqa: F401
from app.models import note as _model_note  # noqa: F401
from app.models import organization as _model_organization  # noqa: F401
from app.models import project as _model_project  # noqa: F401
from app.models import task as _model_task  # noqa: F401
from app.models import user as _model_user  # noqa: F401
from app.models import whatsapp_message as _model_whatsapp_message  # noqa: F401
from app.models import chat_message as _model_chat_message  # noqa: F401
from app.models import ai_call_log as _model_ai_call_log  # noqa: F401
from app.models import employee as _model_employee  # noqa: F401
from app.models import integration_signal as _model_integration_signal  # noqa: F401
from app.models import ops_metrics as _model_ops_metrics  # noqa: F401
from app.models import decision_log as _model_decision_log  # noqa: F401
from app.models import policy_rule as _model_policy_rule  # noqa: F401
from app.models import weekly_report as _model_weekly_report  # noqa: F401

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
    token = create_access_token(
        {"id": 1, "email": "ceo@org1.com", "role": "CEO", "org_id": 1}
    )

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac

    # Teardown: remove overrides and wipe the test database
    fastapi_app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
