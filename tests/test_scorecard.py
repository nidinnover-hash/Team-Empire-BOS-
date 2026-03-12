"""Tests for the unified scorecard endpoint (/api/v1/scorecard)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.main import app as fastapi_app


def _headers(user_id: int = 1, org_id: int = 1, role: str = "CEO") -> dict[str, str]:
    token = create_access_token(
        {"id": user_id, "email": f"user{user_id}@org{org_id}.com", "role": role, "org_id": org_id, "token_version": 1},
    )
    return {"Authorization": f"Bearer {token}"}


# ── Basic access ───────────────────────────────────────────────────────────────

async def test_scorecard_returns_200_for_ceo(client):
    resp = await client.get("/api/v1/scorecard", headers=_headers())
    assert resp.status_code == 200


async def test_scorecard_response_shape(client):
    resp = await client.get("/api/v1/scorecard", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert "window_days" in body
    assert isinstance(body["tiles"], list)


async def test_scorecard_tile_fields(client):
    resp = await client.get("/api/v1/scorecard", headers=_headers())
    assert resp.status_code == 200
    for tile in resp.json()["tiles"]:
        assert "key" in tile
        assert "label" in tile
        assert "value" in tile
        assert "band" in tile
        assert tile["band"] in ("green", "amber", "red")


async def test_scorecard_window_days_param(client):
    resp = await client.get("/api/v1/scorecard?window_days=7", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["window_days"] == 7


async def test_scorecard_window_days_clamped_max(client):
    """window_days > 31 is rejected by Query(ge=1, le=31) → 422."""
    resp = await client.get("/api/v1/scorecard?window_days=999", headers=_headers())
    assert resp.status_code == 422


async def test_scorecard_manager_gets_200(client):
    """MANAGER is in the allowed roles list."""
    resp = await client.get("/api/v1/scorecard", headers=_headers(user_id=3, role="MANAGER"))
    assert resp.status_code == 200


# ── RBAC ──────────────────────────────────────────────────────────────────────

async def test_scorecard_staff_gets_403(client):
    """STAFF (user_id=4) is not in allowed roles for scorecard."""
    resp = await client.get("/api/v1/scorecard", headers=_headers(user_id=4, role="STAFF"))
    assert resp.status_code == 403


async def test_scorecard_no_auth_gets_401(client, _test_engine):
    """Request with no Authorization header is rejected with 401."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from app.core.deps import get_db

    TestSession = async_sessionmaker(bind=_test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override():
        async with TestSession() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = _override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as anon:
            resp = await anon.get("/api/v1/scorecard")
        assert resp.status_code == 401
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


# ── Isolation ─────────────────────────────────────────────────────────────────

async def test_scorecard_wrong_org_rejected(client):
    """Token for org_id=2 with user_id=1 (who belongs to org 1) is rejected."""
    resp = await client.get("/api/v1/scorecard", headers=_headers(user_id=1, org_id=2))
    assert resp.status_code in (401, 403)


# ── Industry dispatch ─────────────────────────────────────────────────────────

async def test_scorecard_unknown_industry_returns_empty_tiles(client, monkeypatch):
    """Org with no/unknown industry_type returns empty tiles list."""
    import app.services.organization as org_svc

    class _FakeOrg:
        industry_type = "unknown_industry_xyz"

    async def _fake_get(db, org_id):
        return _FakeOrg()

    monkeypatch.setattr(org_svc, "get_organization_by_id", _fake_get)
    resp = await client.get("/api/v1/scorecard", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["tiles"] == []
