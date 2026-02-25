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
os.environ.setdefault("PURPOSE_PERSONAL_EMAILS", "nidinnover@gmail.com,purpose-login@gmail.com")
os.environ.setdefault("WHATSAPP_APP_SECRET", "test-whatsapp-secret")
os.environ["DEBUG"] = "true"
os.environ["ENFORCE_STARTUP_VALIDATION"] = "false"
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.deps import get_db
from app.core.security import create_access_token
from app.db.base import Base
from app.main import app as fastapi_app
from app.models.organization import Organization
from app.models.user import User

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
from app.models import ceo_control as _model_ceo_control  # noqa: F401
from app.models import github as _model_github  # noqa: F401
from app.models import social as _model_social  # noqa: F401
from app.models import clone_control as _model_clone_control  # noqa: F401
from app.models import clone_performance as _model_clone_performance  # noqa: F401
from app.models import org_membership as _model_org_membership  # noqa: F401
from app.models import org_role_permission as _model_org_role_permission  # noqa: F401
from app.models import threat_signal as _model_threat_signal  # noqa: F401
from app.models import media_project as _model_media_project  # noqa: F401

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

    # Seed standard test users so JWT auth resolves against the DB.
    # Tests that use _auth_headers() must match these emails and user IDs.
    async with TestSession() as seed_session:
        seed_session.add(Organization(id=1, name="Test Org", slug="test-org"))
        seed_session.add(Organization(id=2, name="Test Org 2", slug="test-org-2"))
        seed_session.add(User(id=1, organization_id=1, name="Test CEO",
                              email="ceo@org1.com", password_hash="unused",
                              role="CEO", is_active=True, token_version=1))
        seed_session.add(User(id=2, organization_id=2, name="Test CEO 2",
                              email="ceo@org2.com", password_hash="unused",
                              role="CEO", is_active=True, token_version=1))
        seed_session.add(User(id=3, organization_id=1, name="Test Manager",
                              email="manager@org1.com", password_hash="unused",
                              role="MANAGER", is_active=True, token_version=1))
        seed_session.add(User(id=4, organization_id=1, name="Test Staff",
                              email="staff@org1.com", password_hash="unused",
                              role="STAFF", is_active=True, token_version=1))
        seed_session.add(User(id=5, organization_id=1, name="Personal CEO",
                              email="nidinnover@gmail.com", password_hash="unused",
                              role="CEO", is_active=True, token_version=1))
        await seed_session.commit()

    async def override_get_db():
        async with TestSession() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    token = create_access_token(
        {
            "id": 1,
            "email": "ceo@org1.com",
            "role": "CEO",
            "org_id": 1,
            "token_version": 1,
            "purpose": "professional",
            "default_theme": "light",
            "default_avatar_mode": "professional",
        }
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
