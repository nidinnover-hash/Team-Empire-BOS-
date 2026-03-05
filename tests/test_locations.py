"""Tests for Maps & Location Tracking endpoints."""

from contextlib import suppress

import pytest

from app.models.employee import Employee
from tests.conftest import _make_auth_headers

# ── Helper ────────────────────────────────────────────────────────────────

async def _seed_employee(client, org_id=1, employee_id=10, consent=False):
    """Seed an Employee record via raw DB insert (conftest only seeds Users)."""
    from app.core.deps import get_db
    from app.main import app

    override = app.dependency_overrides.get(get_db)
    if override is None:
        return
    gen = override()
    db = await gen.__anext__()
    emp = Employee(
        id=employee_id,
        organization_id=org_id,
        name="Test Employee",
        email=f"emp{employee_id}@org{org_id}.com",
        job_title="STAFF",
        is_active=True,
        location_tracking_consent=consent,
    )
    db.add(emp)
    await db.commit()
    with suppress(StopAsyncIteration):
        await gen.__anext__()
    return emp


def _track_payload(employee_id=10, **overrides):
    data = {
        "employee_id": employee_id,
        "latitude": 25.2048,
        "longitude": 55.2708,
        "source": "gps",
    }
    data.update(overrides)
    return data


def _checkin_payload(employee_id=10, **overrides):
    data = {
        "employee_id": employee_id,
        "latitude": 25.2048,
        "longitude": 55.2708,
        "checkin_type": "arrival",
    }
    data.update(overrides)
    return data


# ── POST /locations/track ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_location_returns_201(client):
    await _seed_employee(client)
    r = await client.post("/api/v1/locations/track", json=_track_payload())
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_track_location_returns_correct_fields(client):
    await _seed_employee(client)
    r = await client.post("/api/v1/locations/track", json=_track_payload())
    body = r.json()
    assert body["latitude"] == 25.2048
    assert body["longitude"] == 55.2708
    assert body["source"] == "gps"
    assert body["is_active"] is True
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_track_location_with_accuracy_and_altitude(client):
    await _seed_employee(client)
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(accuracy_m=15.5, altitude_m=42.0),
    )
    body = r.json()
    assert body["accuracy_m"] == 15.5
    assert body["altitude_m"] == 42.0


@pytest.mark.asyncio
async def test_track_location_with_address_and_ip(client):
    await _seed_employee(client)
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(
            source="ip_geolocation",
            address="123 Main St, Dubai",
            ip_address="192.168.1.1",
        ),
    )
    body = r.json()
    assert body["source"] == "ip_geolocation"
    assert body["address"] == "123 Main St, Dubai"
    assert body["ip_address"] == "192.168.1.1"


@pytest.mark.asyncio
async def test_track_location_marks_previous_inactive(client):
    await _seed_employee(client)
    r1 = await client.post("/api/v1/locations/track", json=_track_payload())
    first_id = r1.json()["id"]
    r2 = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(latitude=25.3, longitude=55.3),
    )
    assert r2.json()["is_active"] is True
    # Verify old one is no longer active via history
    history = await client.get("/api/v1/locations/history?employee_id=10")
    items = history.json()
    old = next((x for x in items if x["id"] == first_id), None)
    assert old is not None
    assert old["is_active"] is False


@pytest.mark.asyncio
async def test_track_location_invalid_latitude_returns_422(client):
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(latitude=91.0),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_track_location_invalid_longitude_returns_422(client):
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(longitude=181.0),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_track_location_invalid_source_returns_422(client):
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(source="unknown_source"),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_track_location_missing_employee_id_returns_422(client):
    r = await client.post(
        "/api/v1/locations/track",
        json={"latitude": 25.0, "longitude": 55.0, "source": "gps"},
    )
    assert r.status_code == 422


# ── GET /locations/active ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_locations_empty(client):
    r = await client.get("/api/v1/locations/active")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_active_locations_returns_consented_employee(client):
    await _seed_employee(client, consent=True)
    await client.post("/api/v1/locations/track", json=_track_payload())
    r = await client.get("/api/v1/locations/active")
    locs = r.json()
    assert len(locs) >= 1
    assert locs[0]["employee_id"] == 10
    assert locs[0]["employee_name"] == "Test Employee"


@pytest.mark.asyncio
async def test_active_locations_excludes_non_consented(client):
    await _seed_employee(client, consent=False)
    await client.post("/api/v1/locations/track", json=_track_payload())
    r = await client.get("/api/v1/locations/active")
    assert r.json() == []


# ── GET /locations/history ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_empty(client):
    r = await client.get("/api/v1/locations/history")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_history_returns_tracked_points(client):
    await _seed_employee(client)
    await client.post("/api/v1/locations/track", json=_track_payload())
    await client.post(
        "/api/v1/locations/track",
        json=_track_payload(latitude=25.3, longitude=55.3),
    )
    r = await client.get("/api/v1/locations/history")
    items = r.json()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_history_filter_by_employee(client):
    await _seed_employee(client, employee_id=10)
    await _seed_employee(client, employee_id=11)
    await client.post("/api/v1/locations/track", json=_track_payload(employee_id=10))
    await client.post("/api/v1/locations/track", json=_track_payload(employee_id=11))
    r = await client.get("/api/v1/locations/history?employee_id=10")
    items = r.json()
    assert len(items) == 1
    assert items[0]["employee_id"] == 10


@pytest.mark.asyncio
async def test_history_filter_by_source(client):
    await _seed_employee(client)
    await client.post("/api/v1/locations/track", json=_track_payload(source="gps"))
    await client.post("/api/v1/locations/track", json=_track_payload(source="ip_geolocation"))
    r = await client.get("/api/v1/locations/history?source=gps")
    items = r.json()
    assert len(items) == 1
    assert items[0]["source"] == "gps"


@pytest.mark.asyncio
async def test_history_pagination(client):
    await _seed_employee(client)
    for i in range(5):
        await client.post(
            "/api/v1/locations/track",
            json=_track_payload(latitude=25.0 + i * 0.01),
        )
    r = await client.get("/api/v1/locations/history?limit=2&offset=0")
    assert len(r.json()) == 2
    r2 = await client.get("/api/v1/locations/history?limit=2&offset=2")
    assert len(r2.json()) == 2
    r3 = await client.get("/api/v1/locations/history?limit=2&offset=4")
    assert len(r3.json()) == 1


# ── POST /locations/checkin ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkin_returns_201(client):
    await _seed_employee(client)
    r = await client.post("/api/v1/locations/checkin", json=_checkin_payload())
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_checkin_returns_correct_fields(client):
    await _seed_employee(client)
    r = await client.post(
        "/api/v1/locations/checkin",
        json=_checkin_payload(place_name="Office HQ", notes="Morning arrival"),
    )
    body = r.json()
    assert body["checkin_type"] == "arrival"
    assert body["place_name"] == "Office HQ"
    assert body["notes"] == "Morning arrival"
    assert body["checked_out_at"] is None
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_checkin_all_types(client):
    await _seed_employee(client)
    for t in ["arrival", "departure", "meeting", "site_visit", "other"]:
        r = await client.post(
            "/api/v1/locations/checkin",
            json=_checkin_payload(checkin_type=t),
        )
        assert r.status_code == 201
        assert r.json()["checkin_type"] == t


@pytest.mark.asyncio
async def test_checkin_invalid_type_returns_422(client):
    r = await client.post(
        "/api/v1/locations/checkin",
        json=_checkin_payload(checkin_type="invalid"),
    )
    assert r.status_code == 422


# ── POST /locations/checkin/{id}/checkout ──────────────────────────────────

@pytest.mark.asyncio
async def test_checkout_returns_200(client):
    await _seed_employee(client)
    create = await client.post("/api/v1/locations/checkin", json=_checkin_payload())
    cid = create.json()["id"]
    r = await client.post(f"/api/v1/locations/checkin/{cid}/checkout")
    assert r.status_code == 200
    assert r.json()["checked_out_at"] is not None


@pytest.mark.asyncio
async def test_checkout_nonexistent_returns_404(client):
    r = await client.post("/api/v1/locations/checkin/99999/checkout")
    assert r.status_code == 404


# ── GET /locations/checkins ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_checkins_empty(client):
    r = await client.get("/api/v1/locations/checkins")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_checkins_returns_all(client):
    await _seed_employee(client)
    await client.post("/api/v1/locations/checkin", json=_checkin_payload())
    await client.post(
        "/api/v1/locations/checkin",
        json=_checkin_payload(checkin_type="departure"),
    )
    r = await client.get("/api/v1/locations/checkins")
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_list_checkins_filter_by_employee(client):
    await _seed_employee(client, employee_id=10)
    await _seed_employee(client, employee_id=11)
    await client.post("/api/v1/locations/checkin", json=_checkin_payload(employee_id=10))
    await client.post("/api/v1/locations/checkin", json=_checkin_payload(employee_id=11))
    r = await client.get("/api/v1/locations/checkins?employee_id=10")
    items = r.json()
    assert len(items) == 1
    assert items[0]["employee_id"] == 10


# ── PATCH /locations/consent ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_consent_update_enable(client):
    await _seed_employee(client, consent=False)
    r = await client.patch(
        "/api/v1/locations/consent",
        json={"employee_id": 10, "consent": True},
    )
    assert r.status_code == 200
    assert r.json()["consent"] is True


@pytest.mark.asyncio
async def test_consent_update_disable(client):
    await _seed_employee(client, consent=True)
    r = await client.patch(
        "/api/v1/locations/consent",
        json={"employee_id": 10, "consent": False},
    )
    assert r.status_code == 200
    assert r.json()["consent"] is False


@pytest.mark.asyncio
async def test_consent_update_nonexistent_employee_returns_404(client):
    r = await client.patch(
        "/api/v1/locations/consent",
        json={"employee_id": 99999, "consent": True},
    )
    assert r.status_code == 404


# ── GET /locations/consent ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_consent_status(client):
    await _seed_employee(client, consent=True)
    r = await client.get("/api/v1/locations/consent?employee_id=10")
    assert r.status_code == 200
    body = r.json()
    assert body["employee_id"] == 10
    assert body["consent"] is True


@pytest.mark.asyncio
async def test_get_consent_nonexistent_returns_404(client):
    r = await client.get("/api/v1/locations/consent?employee_id=99999")
    assert r.status_code == 404


# ── GET /locations/consent/all ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_all_consent_empty(client):
    r = await client.get("/api/v1/locations/consent/all")
    assert r.status_code == 200
    # May return empty or seeded employees
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_all_consent_returns_employees(client):
    await _seed_employee(client, employee_id=10, consent=True)
    await _seed_employee(client, employee_id=11, consent=False)
    r = await client.get("/api/v1/locations/consent/all")
    items = r.json()
    assert len(items) >= 2
    ids = [i["employee_id"] for i in items]
    assert 10 in ids
    assert 11 in ids


# ── Permission tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_active_locations_requires_manager_role(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF")
    r = await client.get("/api/v1/locations/active", headers=staff_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_history_requires_manager_role(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF")
    r = await client.get("/api/v1/locations/history", headers=staff_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_checkins_requires_manager_role(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF")
    r = await client.get("/api/v1/locations/checkins", headers=staff_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_consent_all_requires_admin_role(client):
    manager_headers = _make_auth_headers(user_id=3, email="manager@org1.com", role="MANAGER")
    r = await client.get("/api/v1/locations/consent/all", headers=manager_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_track_allowed_for_staff(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF")
    await _seed_employee(client)
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(),
        headers=staff_headers,
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_checkin_allowed_for_staff(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF")
    await _seed_employee(client)
    r = await client.post(
        "/api/v1/locations/checkin",
        json=_checkin_payload(),
        headers=staff_headers,
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_consent_update_allowed_for_staff(client):
    staff_headers = _make_auth_headers(user_id=4, email="staff@org1.com", role="STAFF")
    await _seed_employee(client)
    r = await client.patch(
        "/api/v1/locations/consent",
        json={"employee_id": 10, "consent": True},
        headers=staff_headers,
    )
    assert r.status_code == 200


# ── Web page test ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_maps_web_page_loads(client):
    # Web page requires session cookie; direct GET should redirect to login
    r = await client.get("/web/maps", follow_redirects=False)
    # Either 200 (if test has session) or 302 redirect to login
    assert r.status_code in (200, 302, 307)


# ── Validation edge cases ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_location_boundary_latitude(client):
    await _seed_employee(client)
    # Exactly -90 and 90 should be valid
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(latitude=-90.0),
    )
    assert r.status_code == 201
    r2 = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(latitude=90.0),
    )
    assert r2.status_code == 201


@pytest.mark.asyncio
async def test_track_location_boundary_longitude(client):
    await _seed_employee(client)
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(longitude=-180.0),
    )
    assert r.status_code == 201
    r2 = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(longitude=180.0),
    )
    assert r2.status_code == 201


@pytest.mark.asyncio
async def test_track_location_negative_accuracy_returns_422(client):
    r = await client.post(
        "/api/v1/locations/track",
        json=_track_payload(accuracy_m=-5.0),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_track_all_sources(client):
    await _seed_employee(client)
    for src in ["gps", "ip_geolocation", "manual_checkin", "google_maps"]:
        r = await client.post(
            "/api/v1/locations/track",
            json=_track_payload(source=src),
        )
        assert r.status_code == 201, f"Source {src} should be valid"
