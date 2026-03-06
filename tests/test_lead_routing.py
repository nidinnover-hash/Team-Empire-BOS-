from app.core.security import create_access_token


def _headers(*, user_id: int, email: str, role: str, org_id: int) -> dict[str, str]:
    token = create_access_token(
        {
            "id": user_id,
            "email": email,
            "role": role,
            "org_id": org_id,
            "token_version": 1,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _org2_headers() -> dict[str, str]:
    return _headers(user_id=2, email="ceo@org2.com", role="CEO", org_id=2)


def _org1_staff_headers() -> dict[str, str]:
    return _headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)


def _org1_manager_headers() -> dict[str, str]:
    return _headers(user_id=3, email="manager@org1.com", role="MANAGER", org_id=1)


async def test_lead_defaults_to_empire_owner_and_unrouted(client):
    resp = await client.post("/api/v1/contacts", json={"name": "Lead Default"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["lead_owner_company_id"] == 1
    assert body["routing_status"] == "unrouted"
    assert body["routed_company_id"] is None
    assert body["lead_type"] == "general"


async def test_route_contact_by_lead_type_auto(client):
    created = await client.post("/api/v1/contacts", json={"name": "Lead Auto Route", "lead_type": "study_abroad"})
    contact_id = created.json()["id"]
    routed = await client.post(
        f"/api/v1/contacts/{contact_id}/route",
        json={"lead_type": "study_abroad"},
    )
    assert routed.status_code == 200
    body = routed.json()
    assert body["contact_id"] == contact_id
    assert body["lead_type"] == "study_abroad"
    assert body["routing_status"] == "routed"
    assert body["routed_company_id"] == 2
    assert body["routed_by_user_id"] == 1
    assert body["routed_at"] is not None


async def test_manual_routing_overrides_auto_mapping(client):
    created = await client.post("/api/v1/contacts", json={"name": "Lead Manual Route", "lead_type": "recruitment"})
    contact_id = created.json()["id"]
    routed = await client.post(
        f"/api/v1/contacts/{contact_id}/route",
        json={"lead_type": "recruitment", "routed_company_id": 2},
    )
    assert routed.status_code == 200
    body = routed.json()
    assert body["routing_status"] == "routed"
    assert body["routed_company_id"] == 2


async def test_routing_changes_service_company_visibility(client):
    hidden = await client.post("/api/v1/contacts", json={"name": "Not Routed Lead"})
    assert hidden.status_code == 201
    visible = await client.post("/api/v1/contacts", json={"name": "Routed Lead", "lead_type": "study_abroad"})
    routed_id = visible.json()["id"]
    route_resp = await client.post(
        f"/api/v1/contacts/{routed_id}/route",
        json={"lead_type": "study_abroad"},
    )
    assert route_resp.status_code == 200

    org2_list = await client.get("/api/v1/contacts", headers=_org2_headers())
    assert org2_list.status_code == 200
    names = {c["name"] for c in org2_list.json()}
    assert "Routed Lead" in names
    assert "Not Routed Lead" not in names


async def test_staff_cannot_access_cross_company_routed_leads(client):
    created = await client.post("/api/v1/contacts", json={"name": "Staff Hidden Routed"})
    contact_id = created.json()["id"]
    route_resp = await client.post(
        f"/api/v1/contacts/{contact_id}/route",
        json={"lead_type": "study_abroad"},
    )
    assert route_resp.status_code == 200

    staff_list = await client.get("/api/v1/contacts", headers=_org1_staff_headers())
    assert staff_list.status_code == 200
    names = {c["name"] for c in staff_list.json()}
    assert "Staff Hidden Routed" not in names


async def test_manager_sees_only_company_local_leads(client):
    local = await client.post("/api/v1/contacts", json={"name": "Manager Local Lead"})
    assert local.status_code == 201
    routed_out = await client.post("/api/v1/contacts", json={"name": "Manager Routed Out"})
    routed_out_id = routed_out.json()["id"]
    route_resp = await client.post(
        f"/api/v1/contacts/{routed_out_id}/route",
        json={"lead_type": "study_abroad"},
    )
    assert route_resp.status_code == 200

    mgr_list = await client.get("/api/v1/contacts", headers=_org1_manager_headers())
    assert mgr_list.status_code == 200
    names = {c["name"] for c in mgr_list.json()}
    assert "Manager Local Lead" in names
    assert "Manager Routed Out" not in names
