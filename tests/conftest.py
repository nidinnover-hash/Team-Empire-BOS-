"""
Shared test fixtures.

Every test gets:
  - A fresh in-memory SQLite database (never touches the production DB)
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
os.environ.setdefault("DASHBOARD_CACHE_TTL_SECONDS", "0")
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.deps import get_db
from app.core.security import create_access_token
from app.db.base import Base
from app.main import app as fastapi_app
from app.models.organization import Organization
from app.models.registry import load_all_models
from app.models.user import User

# Register all models so Base.metadata knows about every table.
load_all_models()

# StaticPool + check_same_thread=False makes all connections share one
# in-memory SQLite database — required for :memory: to work across requests.
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _reset_redis_module_state():
    """Force all Redis-backed modules to use in-memory fallback during tests.

    The production .env file sets RATE_LIMIT_REDIS_URL and IDEMPOTENCY_REDIS_URL
    to real Redis addresses.  Pydantic Settings reads these into the ``settings``
    singleton at import time (and ``env_ignore_empty=True`` prevents us from
    simply setting the env var to "").

    This autouse fixture:
      1. Blanks the two Redis URL settings so every ``_redis_url()`` / URL check
         returns "" and the module skips Redis entirely.
      2. Resets the ``_redis_initialized`` / ``_redis_client`` cached state in
         every module that lazily creates a Redis connection, so stale clients
         from a previous test are never reused.

    Together this guarantees every module falls back to its in-memory code path
    and no test ever attempts a real Redis connection.
    """
    from app.api.v1.endpoints import email as email_mod
    from app.core import idempotency as idempotency_mod
    from app.core import middleware as middleware_mod
    from app.core import oauth_nonce as nonce_mod
    from app.core.config import settings

    # --- 1. Blank Redis URL settings ---
    saved_settings = {
        "rate_limit_redis_url": settings.RATE_LIMIT_REDIS_URL,
        "idempotency_redis_url": settings.IDEMPOTENCY_REDIS_URL,
    }
    object.__setattr__(settings, "RATE_LIMIT_REDIS_URL", None)
    object.__setattr__(settings, "IDEMPOTENCY_REDIS_URL", None)

    # --- 2. Reset module-level Redis caches ---
    saved_modules = {
        "nonce_init": nonce_mod._redis_initialized,
        "nonce_client": nonce_mod._redis_client,
        "idem_init": idempotency_mod._redis_initialized,
        "idem_client": idempotency_mod._redis_client,
        "mw_init": middleware_mod._redis_initialized,
        "mw_client": middleware_mod._redis_client,
        "email_init": email_mod._compose_redis_initialized,
        "email_client": email_mod._compose_redis_client,
    }

    nonce_mod._redis_initialized = False
    nonce_mod._redis_client = None
    idempotency_mod._redis_initialized = False
    idempotency_mod._redis_client = None
    middleware_mod._redis_initialized = False
    middleware_mod._redis_client = None
    email_mod._compose_redis_initialized = False
    email_mod._compose_redis_client = None

    yield

    # --- Restore original state ---
    object.__setattr__(settings, "RATE_LIMIT_REDIS_URL", saved_settings["rate_limit_redis_url"])
    object.__setattr__(settings, "IDEMPOTENCY_REDIS_URL", saved_settings["idempotency_redis_url"])

    nonce_mod._redis_initialized = saved_modules["nonce_init"]
    nonce_mod._redis_client = saved_modules["nonce_client"]
    idempotency_mod._redis_initialized = saved_modules["idem_init"]
    idempotency_mod._redis_client = saved_modules["idem_client"]
    middleware_mod._redis_initialized = saved_modules["mw_init"]
    middleware_mod._redis_client = saved_modules["mw_client"]
    email_mod._compose_redis_initialized = saved_modules["email_init"]
    email_mod._compose_redis_client = saved_modules["email_client"]


@pytest.fixture(autouse=True)
def _reset_auth_runtime_state():
    """Stabilize auth-related mutable globals between tests."""
    from app.core import middleware as middleware_mod
    from app.core.config import settings

    saved_values = {
        "ACCOUNT_SSO_REQUIRED": settings.ACCOUNT_SSO_REQUIRED,
        "ACCESS_TOKEN_EXPIRE_MINUTES": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "ACCOUNT_SESSION_MAX_HOURS": settings.ACCOUNT_SESSION_MAX_HOURS,
    }
    object.__setattr__(settings, "ACCOUNT_SSO_REQUIRED", False)

    with middleware_mod._login_lock:
        middleware_mod._login_failures.clear()

    yield

    object.__setattr__(settings, "ACCOUNT_SSO_REQUIRED", saved_values["ACCOUNT_SSO_REQUIRED"])
    object.__setattr__(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", saved_values["ACCESS_TOKEN_EXPIRE_MINUTES"])
    object.__setattr__(settings, "ACCOUNT_SESSION_MAX_HOURS", saved_values["ACCOUNT_SESSION_MAX_HOURS"])

async def _seed_db(session_factory, *, full: bool = True):
    """Seed standard test orgs and users.

    When ``full=True`` (used by the ``client`` fixture), seeds all 5 users.
    When ``full=False`` (used by the ``db`` fixture), seeds only the 2 CEOs.
    """
    async with session_factory() as s:
        s.add(Organization(id=1, name="Test Org", slug="test-org"))
        s.add(Organization(id=2, name="Test Org 2", slug="test-org-2"))
        s.add(User(id=1, organization_id=1, name="Test CEO",
                    email="ceo@org1.com", password_hash="unused",
                    role="CEO", is_active=True, token_version=1,
                    is_super_admin=True))
        s.add(User(id=2, organization_id=2, name="Test CEO 2",
                    email="ceo@org2.com", password_hash="unused",
                    role="CEO", is_active=True, token_version=1))
        if full:
            s.add(User(id=3, organization_id=1, name="Test Manager",
                        email="manager@org1.com", password_hash="unused",
                        role="MANAGER", is_active=True, token_version=1))
            s.add(User(id=4, organization_id=1, name="Test Staff",
                        email="staff@org1.com", password_hash="unused",
                        role="STAFF", is_active=True, token_version=1))
            s.add(User(id=5, organization_id=1, name="Personal CEO",
                        email="nidinnover@gmail.com", password_hash="unused",
                        role="CEO", is_active=True, token_version=1))
        await s.commit()


@pytest_asyncio.fixture
async def _test_engine():
    """Shared in-memory SQLite engine for a single test (used by both client and db)."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(_test_engine):
    """Async DB session backed by the test in-memory database.

    Use for tests that call service / job functions directly (not via HTTP).
    Shares the same engine as the ``client`` fixture when both are requested.
    """
    TestSession = async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    await _seed_db(TestSession, full=False)

    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(_test_engine):
    TestSession = async_sessionmaker(
        bind=_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    await _seed_db(TestSession, full=True)

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


def _make_auth_headers(
    user_id: int = 1,
    email: str = "ceo@org1.com",
    role: str = "CEO",
    org_id: int = 1,
) -> dict[str, str]:
    """Create Authorization headers with a JWT for the specified user."""
    token = create_access_token(
        {"id": user_id, "email": email, "role": role, "org_id": org_id, "token_version": 1},
    )
    return {"Authorization": f"Bearer {token}"}
