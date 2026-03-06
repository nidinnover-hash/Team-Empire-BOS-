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


def _org1_ceo_headers() -> dict[str, str]:
    return _headers(user_id=1, email="ceo@org1.com", role="CEO", org_id=1)


def _org1_staff_headers() -> dict[str, str]:
    return _headers(user_id=4, email="staff@org1.com", role="STAFF", org_id=1)


def _org2_ceo_headers() -> dict[str, str]:
    return _headers(user_id=2, email="ceo@org2.com", role="CEO", org_id=2)


async def _org1_events(client):
    resp = await client.get("/api/v1/ops/events?limit=100", headers=_org1_ceo_headers())
    assert resp.status_code == 200
    return resp.json()


async def test_empire_cockpit_cross_company_for_empire_ceo(client):
    lead_local = await client.post("/api/v1/contacts", json={"name": "Empire Local", "lead_type": "general"})
    assert lead_local.status_code == 201

    lead_routed = await client.post("/api/v1/contacts", json={"name": "Empire Routed", "lead_type": "study_abroad"})
    assert lead_routed.status_code == 201
    route = await client.post(f"/api/v1/contacts/{lead_routed.json()['id']}/route", json={"lead_type": "study_abroad"})
    assert route.status_code == 200

    cockpit = await client.get("/api/v1/empire-digital/cockpit", headers=_org1_ceo_headers())
    assert cockpit.status_code == 200
    body = cockpit.json()
    assert body["visibility_scope"] == "cross_company"
    assert body["total_visible_leads"] >= 2
    assert body["unrouted_leads"] >= 1
    assert body["routed_leads"] >= 1
    assert "unrouted_aging_buckets" in body
    assert "average_routing_hours" in body
    routed_items = [row for row in body.get("by_routed_company", []) if row.get("key") != "unrouted"]
    if routed_items:
        assert routed_items[0].get("label")


async def test_service_company_cockpit_is_scoped_to_routed_leads(client):
    hidden = await client.post("/api/v1/contacts", json={"name": "Hidden For Org2", "lead_type": "general"})
    assert hidden.status_code == 201
    visible = await client.post("/api/v1/contacts", json={"name": "Visible For Org2", "lead_type": "study_abroad"})
    assert visible.status_code == 201
    route = await client.post(f"/api/v1/contacts/{visible.json()['id']}/route", json={"lead_type": "study_abroad"})
    assert route.status_code == 200

    cockpit = await client.get("/api/v1/empire-digital/cockpit", headers=_org2_ceo_headers())
    assert cockpit.status_code == 200
    body = cockpit.json()
    assert body["visibility_scope"] == "company_scoped"
    assert body["total_visible_leads"] >= 1
    assert body["unrouted_leads"] == 0


async def test_staff_cannot_access_empire_cockpit(client):
    resp = await client.get("/api/v1/empire-digital/cockpit", headers=_org1_staff_headers())
    assert resp.status_code == 403


async def test_non_empire_org_cannot_manage_routing_rules(client):
    resp = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org2_ceo_headers(),
        json={"lead_type": "general", "target_company_id": 2, "priority": 10},
    )
    assert resp.status_code == 403


async def test_marketing_intelligence_submission_scoping_and_review(client):
    submit = await client.post(
        "/api/v1/empire-digital/intelligence",
        headers=_org2_ceo_headers(),
        json={
            "category": "market_demand",
            "title": "Australia demand rising",
            "summary": "Australia nursing demand is rising rapidly this month.",
            "confidence": 0.8,
            "priority": "high",
            "suggested_action": "Increase campaign budget for nursing audiences.",
        },
    )
    assert submit.status_code == 201
    item = submit.json()
    assert item["owner_company_id"] == 1
    assert item["source_company_id"] == 2
    assert item["status"] == "submitted"

    org2_list = await client.get("/api/v1/empire-digital/intelligence", headers=_org2_ceo_headers())
    assert org2_list.status_code == 200
    assert any(row["id"] == item["id"] for row in org2_list.json())

    org1_list = await client.get("/api/v1/empire-digital/intelligence", headers=_org1_ceo_headers())
    assert org1_list.status_code == 200
    assert any(row["id"] == item["id"] for row in org1_list.json())

    denied_review = await client.post(
        f"/api/v1/empire-digital/intelligence/{item['id']}/review",
        headers=_org2_ceo_headers(),
        json={"status": "accepted"},
    )
    assert denied_review.status_code == 403

    accepted_review = await client.post(
        f"/api/v1/empire-digital/intelligence/{item['id']}/review",
        headers=_org1_ceo_headers(),
        json={"status": "accepted", "create_decision_card": True},
    )
    assert accepted_review.status_code == 200
    review_body = accepted_review.json()
    assert review_body["item"]["status"] == "accepted"
    assert isinstance(review_body["decision_card_id"], int)
    decision_card_id = review_body["decision_card_id"]
    decision_card = await client.get(f"/api/v1/decision-cards/{decision_card_id}", headers=_org1_ceo_headers())
    assert decision_card.status_code == 200
    assert decision_card.json()["source_type"] == "marketing_intelligence"
    assert decision_card.json()["source_id"] == str(item["id"])


async def test_empire_routing_rule_can_override_general_auto_routing(client):
    created_rule = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={
            "lead_type": "general",
            "target_company_id": 2,
            "priority": 5,
            "routing_reason": "phase2 general route to org2",
        },
    )
    assert created_rule.status_code == 201
    rule_id = created_rule.json()["id"]

    created_contact = await client.post(
        "/api/v1/contacts",
        json={"name": "General Routed by Rule", "lead_type": "general"},
    )
    assert created_contact.status_code == 201
    contact_id = created_contact.json()["id"]
    routed = await client.post(
        f"/api/v1/contacts/{contact_id}/route",
        json={"lead_type": "general"},
    )
    assert routed.status_code == 200
    routed_body = routed.json()
    assert routed_body["routed_company_id"] == 2
    assert "phase2 general route to org2" in (routed_body["routing_reason"] or "")

    listed_rules = await client.get("/api/v1/empire-digital/routing-rules?active_only=true", headers=_org1_ceo_headers())
    assert listed_rules.status_code == 200
    assert any(row["id"] == rule_id for row in listed_rules.json())
    events = await _org1_events(client)
    assert any(e["event_type"] == "lead_routing_rule_created" for e in events)


async def test_routing_rule_validation_for_duplicate_priority_and_target_company(client):
    first = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={"lead_type": "general", "target_company_id": 2, "priority": 25},
    )
    assert first.status_code == 201
    duplicate_priority = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={"lead_type": "general", "target_company_id": 1, "priority": 25},
    )
    assert duplicate_priority.status_code == 409

    invalid_target = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={"lead_type": "general", "target_company_id": 9999, "priority": 26},
    )
    assert invalid_target.status_code == 422


async def test_routing_rule_priority_ordering_applies_lowest_priority_number(client):
    low = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={"lead_type": "general", "target_company_id": 2, "priority": 10},
    )
    assert low.status_code == 201
    high = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={"lead_type": "general", "target_company_id": 1, "priority": 50},
    )
    assert high.status_code == 201
    created_contact = await client.post("/api/v1/contacts", json={"name": "Priority Rule Lead", "lead_type": "general"})
    assert created_contact.status_code == 201
    routed = await client.post(f"/api/v1/contacts/{created_contact.json()['id']}/route", json={"lead_type": "general"})
    assert routed.status_code == 200
    body = routed.json()
    assert body["routing_source"] == "rule"
    assert body["routed_company_id"] == 2


async def test_routing_rule_deactivate_writes_audit_event(client):
    created = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={"lead_type": "recruitment", "target_company_id": 2, "priority": 12},
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]
    updated = await client.patch(
        f"/api/v1/empire-digital/routing-rules/{rule_id}",
        headers=_org1_ceo_headers(),
        json={"is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False
    events = await _org1_events(client)
    assert any(e["event_type"] == "lead_routing_rule_updated" and e.get("entity_id") == rule_id for e in events)


async def test_manual_route_overrides_rule_and_clears_rule_reference(client):
    rule = await client.post(
        "/api/v1/empire-digital/routing-rules",
        headers=_org1_ceo_headers(),
        json={"lead_type": "study_abroad", "target_company_id": 1, "priority": 7},
    )
    assert rule.status_code == 201
    lead = await client.post("/api/v1/contacts", json={"name": "Manual Override Lead", "lead_type": "study_abroad"})
    assert lead.status_code == 201
    routed = await client.post(
        f"/api/v1/contacts/{lead.json()['id']}/route",
        json={"lead_type": "study_abroad", "routed_company_id": 2, "routing_reason": "manual_override"},
    )
    assert routed.status_code == 200
    body = routed.json()
    assert body["routing_source"] == "manual"
    assert body["routing_rule_id"] is None
    assert body["routed_company_id"] == 2


async def test_sla_policy_threshold_drives_cockpit_warning(client):
    update = await client.patch(
        "/api/v1/empire-digital/sla-policy",
        headers=_org1_ceo_headers(),
        json={"stale_unrouted_days": 1, "warning_stale_count": 1, "warning_unrouted_count": 2},
    )
    assert update.status_code == 200
    await client.post("/api/v1/contacts", json={"name": "Warn A"})
    await client.post("/api/v1/contacts", json={"name": "Warn B"})
    cockpit = await client.get("/api/v1/empire-digital/cockpit", headers=_org1_ceo_headers())
    assert cockpit.status_code == 200
    body = cockpit.json()
    assert body["stale_warning_threshold_count"] == 1
    assert body["warning_unrouted_threshold_count"] == 2
    assert body["stale_warning_triggered"] is True


async def test_bulk_route_and_qualify_endpoints(client):
    c1 = await client.post("/api/v1/contacts", json={"name": "Bulk A"})
    c2 = await client.post("/api/v1/contacts", json={"name": "Bulk B"})
    ids = [c1.json()["id"], c2.json()["id"]]
    bulk_route = await client.post(
        "/api/v1/empire-digital/leads/bulk-route",
        headers=_org1_ceo_headers(),
        json={"contact_ids": ids, "lead_type": "general", "routed_company_id": 2},
    )
    assert bulk_route.status_code == 200
    assert bulk_route.json()["updated"] == 2
    bulk_qualify = await client.post(
        "/api/v1/empire-digital/leads/bulk-qualify",
        headers=_org1_ceo_headers(),
        json={"contact_ids": ids, "qualified_score": 70, "qualified_status": "qualified"},
    )
    assert bulk_qualify.status_code == 200
    assert bulk_qualify.json()["updated"] == 2
    events = await _org1_events(client)
    assert any(e["event_type"] == "bulk_contact_routed" for e in events)
    assert any(e["event_type"] == "bulk_contact_qualified" for e in events)


async def test_intelligence_review_event_contains_decision_card_id(client):
    submit = await client.post(
        "/api/v1/empire-digital/intelligence",
        headers=_org2_ceo_headers(),
        json={"category": "other", "title": "Routing quality", "summary": "Need tighter screening."},
    )
    assert submit.status_code == 201
    item_id = submit.json()["id"]
    review = await client.post(
        f"/api/v1/empire-digital/intelligence/{item_id}/review",
        headers=_org1_ceo_headers(),
        json={"status": "accepted", "create_decision_card": True},
    )
    assert review.status_code == 200
    decision_card_id = review.json()["decision_card_id"]
    assert decision_card_id is not None
    events = await _org1_events(client)
    matched = [
        e for e in events
        if e["event_type"] == "marketing_intelligence_reviewed" and e.get("entity_id") == item_id
    ]
    assert matched
    assert matched[0]["payload_json"].get("decision_card_id") == decision_card_id


async def test_founder_report_endpoint_returns_daily_points(client):
    await client.post("/api/v1/contacts", json={"name": "Report Lead"})
    report = await client.get("/api/v1/empire-digital/founder-report?window_days=5", headers=_org1_ceo_headers())
    assert report.status_code == 200
    body = report.json()
    assert body["window_days"] == 5
    assert len(body["points"]) == 5


async def test_lead_detail_endpoint_returns_routing_explainability(client):
    lead = await client.post("/api/v1/contacts", json={"name": "Lead Detail", "lead_type": "general"})
    assert lead.status_code == 201
    lead_id = lead.json()["id"]
    routed = await client.post(
        f"/api/v1/contacts/{lead_id}/route",
        json={"lead_type": "general", "routed_company_id": 2, "routing_reason": "manual_from_test"},
    )
    assert routed.status_code == 200

    detail = await client.get(f"/api/v1/empire-digital/leads/{lead_id}", headers=_org1_ceo_headers())
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == lead_id
    assert body["routing_source"] == "manual"
    assert body["routing_rule_id"] is None
    assert body["routed_company_id"] == 2


async def test_bulk_qualify_invalid_transition_is_skipped(client):
    lead = await client.post("/api/v1/contacts", json={"name": "Invalid Transition Lead"})
    assert lead.status_code == 201
    lead_id = lead.json()["id"]
    resp = await client.post(
        "/api/v1/empire-digital/leads/bulk-qualify",
        headers=_org1_ceo_headers(),
        json={"contact_ids": [lead_id], "routing_status": "accepted"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 0
    assert body["skipped"] == 1


async def test_lead_export_includes_explainability_and_sla_fields(client):
    created = await client.post("/api/v1/contacts", json={"name": "Export Lead", "lead_type": "general"})
    assert created.status_code == 201

    export_json = await client.get("/api/v1/empire-digital/leads/export?format=json", headers=_org1_ceo_headers())
    assert export_json.status_code == 200
    payload = export_json.json()
    assert "items" in payload
    assert payload["count"] >= 1
    first = payload["items"][0]
    assert "routing_source" in first
    assert "routing_rule_id" in first
    assert "aging_bucket" in first
    assert "stale_by_sla" in first

    export_csv = await client.get("/api/v1/empire-digital/leads/export?format=csv", headers=_org1_ceo_headers())
    assert export_csv.status_code == 200
    text = export_csv.text
    assert "routing_source" in text
    assert "routing_rule_id" in text
    assert "aging_bucket" in text
    assert "stale_by_sla" in text
