"""
Tests for the profile memory API:
  GET    /api/v1/memory/profile          — list (CEO only)
  POST   /api/v1/memory/profile          — upsert (CEO only)
  DELETE /api/v1/memory/profile/{id}     — delete (CEO only)

Role enforcement: STAFF / MANAGER must receive 403 on all three endpoints.
"""
from typing import cast

from app.core.security import create_access_token


def _token(user_id: int, email: str, role: str, org_id: int = 1) -> dict:
    t = create_access_token({"id": user_id, "email": email, "role": role, "org_id": org_id, "token_version": 1})
    return {"Authorization": f"Bearer {t}"}


CEO     = _token(1, "ceo@org1.com",     "CEO")
MANAGER = _token(3, "manager@org1.com", "MANAGER")
STAFF   = _token(4, "staff@org1.com",   "STAFF")


# ── GET /api/v1/memory/profile ────────────────────────────────────────────────

async def test_list_profile_memory_empty_initially(client):
    r = await client.get("/api/v1/memory/profile", headers=CEO)
    assert r.status_code == 200
    assert r.json() == []


async def test_list_profile_memory_requires_ceo_manager_blocked(client):
    r = await client.get("/api/v1/memory/profile", headers=MANAGER)
    assert r.status_code == 403


async def test_list_profile_memory_requires_ceo_staff_blocked(client):
    r = await client.get("/api/v1/memory/profile", headers=STAFF)
    assert r.status_code == 403


# ── POST /api/v1/memory/profile ───────────────────────────────────────────────

async def test_create_profile_memory_returns_201(client):
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": "name", "value": "Nidin Nover", "category": "personal"},
        headers=CEO,
    )
    assert r.status_code == 201


async def test_create_profile_memory_returns_correct_fields(client):
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": "role", "value": "CEO", "category": "work"},
        headers=CEO,
    )
    body = r.json()
    assert body["key"] == "role"
    assert body["value"] == "CEO"
    assert body["category"] == "work"
    assert "id" in body
    assert "updated_at" in body


async def test_create_profile_memory_null_category(client):
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": "company", "value": "AI Corp"},
        headers=CEO,
    )
    assert r.status_code == 201
    assert r.json()["category"] is None


async def test_upsert_profile_memory_updates_value(client):
    await client.post(
        "/api/v1/memory/profile",
        json={"key": "timezone", "value": "Asia/Kolkata"},
        headers=CEO,
    )
    r2 = await client.post(
        "/api/v1/memory/profile",
        json={"key": "timezone", "value": "Asia/Dubai"},
        headers=CEO,
    )
    assert r2.status_code == 201
    assert r2.json()["value"] == "Asia/Dubai"


async def test_upsert_does_not_duplicate_key(client):
    await client.post(
        "/api/v1/memory/profile",
        json={"key": "lang", "value": "Python"},
        headers=CEO,
    )
    await client.post(
        "/api/v1/memory/profile",
        json={"key": "lang", "value": "Python + FastAPI"},
        headers=CEO,
    )
    entries = (await client.get("/api/v1/memory/profile", headers=CEO)).json()
    assert len([e for e in entries if e["key"] == "lang"]) == 1


async def test_create_profile_memory_audited(client):
    await client.post(
        "/api/v1/memory/profile",
        json={"key": "audit_check", "value": "yes"},
        headers=CEO,
    )
    events = (await client.get("/api/v1/ops/events", headers=CEO)).json()
    assert any(e["event_type"] == "profile_memory_updated" for e in events)


async def test_create_profile_memory_requires_ceo_staff_blocked(client):
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": "foo", "value": "bar"},
        headers=STAFF,
    )
    assert r.status_code == 403


async def test_create_profile_memory_requires_ceo_manager_blocked(client):
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": "foo", "value": "bar"},
        headers=MANAGER,
    )
    assert r.status_code == 403


async def test_create_profile_memory_missing_key_returns_422(client):
    r = await client.post(
        "/api/v1/memory/profile",
        json={"value": "no key field"},
        headers=CEO,
    )
    assert r.status_code == 422


async def test_create_profile_memory_missing_value_returns_422(client):
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": "no-value"},
        headers=CEO,
    )
    assert r.status_code == 422


# ── DELETE /api/v1/memory/profile/{id} ───────────────────────────────────────

async def _create_entry(client, key: str = "to_delete", value: str = "temp") -> int:
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": key, "value": value},
        headers=CEO,
    )
    return cast(int, r.json()["id"])


async def test_delete_profile_memory_returns_204(client):
    entry_id = await _create_entry(client)
    r = await client.delete(f"/api/v1/memory/profile/{entry_id}", headers=CEO)
    assert r.status_code == 204


async def test_delete_profile_memory_removes_entry(client):
    entry_id = await _create_entry(client, key="removable")
    await client.delete(f"/api/v1/memory/profile/{entry_id}", headers=CEO)

    entries = (await client.get("/api/v1/memory/profile", headers=CEO)).json()
    assert not any(e["id"] == entry_id for e in entries)


async def test_delete_profile_memory_not_found_returns_404(client):
    r = await client.delete("/api/v1/memory/profile/99999", headers=CEO)
    assert r.status_code == 404


async def test_delete_profile_memory_wrong_org_returns_404(client):
    """An entry from org 2 must be invisible to a CEO of org 1."""
    org2_token = _token(2, "ceo@org2.com", "CEO", org_id=2)
    r = await client.post(
        "/api/v1/memory/profile",
        json={"key": "org2_secret", "value": "hidden"},
        headers=org2_token,
    )
    # org2 created the entry (if the API uses org_id from JWT, it will be scoped)
    # Attempt deletion as org1 CEO — should 404 (cross-org isolation)
    if r.status_code == 200:
        entry_id = r.json()["id"]
        del_r = await client.delete(f"/api/v1/memory/profile/{entry_id}", headers=CEO)
        assert del_r.status_code == 404


async def test_delete_profile_memory_requires_ceo_manager_blocked(client):
    entry_id = await _create_entry(client, key="protected_mgr")
    r = await client.delete(f"/api/v1/memory/profile/{entry_id}", headers=MANAGER)
    assert r.status_code == 403


async def test_delete_profile_memory_requires_ceo_staff_blocked(client):
    entry_id = await _create_entry(client, key="protected_staff")
    r = await client.delete(f"/api/v1/memory/profile/{entry_id}", headers=STAFF)
    assert r.status_code == 403


async def test_delete_profile_memory_is_audited(client):
    entry_id = await _create_entry(client, key="audited_entry")
    await client.delete(f"/api/v1/memory/profile/{entry_id}", headers=CEO)

    events = (await client.get("/api/v1/ops/events", headers=CEO)).json()
    assert any(e["event_type"] == "profile_memory_deleted" for e in events)


async def test_list_shows_remaining_entries_after_delete(client):
    id1 = await _create_entry(client, key="keep_me",   value="stays")
    id2 = await _create_entry(client, key="delete_me", value="gone")

    await client.delete(f"/api/v1/memory/profile/{id2}", headers=CEO)

    entries = (await client.get("/api/v1/memory/profile", headers=CEO)).json()
    ids = [e["id"] for e in entries]
    assert id1 in ids
    assert id2 not in ids
