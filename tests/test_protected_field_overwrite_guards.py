"""Tests for protected-field overwrite prevention in update paths."""
from __future__ import annotations

import pytest

from app.services import deal_split as split_svc
from app.services import product_bundle as bundle_svc
from app.services import quote as quote_svc

# --- Quote service guards ---

def test_quote_protected_fields_set_includes_org_id():
    assert "organization_id" in quote_svc._PROTECTED_FIELDS
    assert "id" in quote_svc._PROTECTED_FIELDS
    assert "created_by_user_id" in quote_svc._PROTECTED_FIELDS
    assert "created_at" in quote_svc._PROTECTED_FIELDS


@pytest.mark.asyncio
async def test_quote_update_cannot_overwrite_id(db):
    q = await quote_svc.create_quote(db, organization_id=1, title="ID Test", created_by_user_id=1)
    original_id = q.id
    updated = await quote_svc.update_quote(db, q.id, organization_id=1, id=9999)
    assert updated is not None
    assert updated.id == original_id


@pytest.mark.asyncio
async def test_quote_update_cannot_overwrite_created_by_user_id(db):
    q = await quote_svc.create_quote(db, organization_id=1, title="Author Test", created_by_user_id=1)
    updated = await quote_svc.update_quote(db, q.id, organization_id=1, created_by_user_id=99)
    assert updated is not None
    assert updated.created_by_user_id == 1


# --- Bundle service guards ---

def test_bundle_protected_fields_set_includes_org_id():
    assert "organization_id" in bundle_svc._PROTECTED_FIELDS
    assert "id" in bundle_svc._PROTECTED_FIELDS
    assert "created_at" in bundle_svc._PROTECTED_FIELDS


@pytest.mark.asyncio
async def test_bundle_update_cannot_overwrite_id(db):
    b = await bundle_svc.create_bundle(db, organization_id=1, name="ID Test", bundle_price=50)
    original_id = b.id
    updated = await bundle_svc.update_bundle(db, b.id, org_id=1, id=8888)
    assert updated is not None
    assert updated.id == original_id


@pytest.mark.asyncio
async def test_bundle_update_cannot_overwrite_organization_id(db):
    b = await bundle_svc.create_bundle(db, organization_id=1, name="Test", bundle_price=100)
    updated = await bundle_svc.update_bundle(db, b.id, org_id=1, name="Changed", organization_id=2)
    assert updated is not None
    assert updated.organization_id == 1
    assert updated.name == "Changed"


# --- Split service guards ---

def test_split_protected_fields_set_includes_org_id():
    assert "organization_id" in split_svc._PROTECTED_FIELDS
    assert "id" in split_svc._PROTECTED_FIELDS
    assert "created_at" in split_svc._PROTECTED_FIELDS


@pytest.mark.asyncio
async def test_split_update_cannot_overwrite_organization_id(db):
    s = await split_svc.create_split(db, organization_id=1, deal_id=1, user_id=1, split_pct=50)
    updated = await split_svc.update_split(db, s.id, org_id=1, organization_id=2)
    assert updated is not None
    assert updated.organization_id == 1


# --- API-level guard (quotes endpoint) ---

@pytest.mark.asyncio
async def test_quote_update_endpoint_rejects_protected_fields(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "FEATURE_QUOTES", True)

    created = await client.post("/api/v1/quotes", json={"title": "API Protected"})
    assert created.status_code == 201
    qid = created.json()["id"]

    updated = await client.put(
        f"/api/v1/quotes/{qid}",
        json={"title": "Safe", "organization_id": 2, "created_by_user_id": 99, "id": 999},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["title"] == "Safe"
    assert body["organization_id"] == 1
    assert body["created_by_user_id"] == 1
    assert body["id"] == qid
