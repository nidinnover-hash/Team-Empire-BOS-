"""Tests for personal branding, fraud detection, AI news digest, and ethical boundary features."""


# ── Personal Branding Power ────────────────────────────────────────────────────

async def test_branding_power_report_empty_org(client):
    r = await client.get("/api/v1/data/branding/power")
    assert r.status_code == 200
    body = r.json()
    assert "branding_score" in body
    assert 0 <= body["branding_score"] <= 100
    assert isinstance(body["platforms_active"], list)
    assert isinstance(body["content_themes"], list)
    assert isinstance(body["strengths"], list)
    assert isinstance(body["gaps"], list)
    assert isinstance(body["next_actions"], list)


async def test_branding_power_via_layers(client):
    r = await client.get("/api/v1/layers/branding-power")
    assert r.status_code == 200
    body = r.json()
    assert "branding_score" in body
    assert "content_consistency" in body
    assert "platform_coverage" in body
    assert "audience_alignment" in body


async def test_branding_power_with_social_content(client):
    # Create a social post to generate branding data
    r = await client.post(
        "/api/v1/social/posts",
        json={
            "content_mode": "social_media",
            "platform": "linkedin",
            "title": "AI in Education: Transforming Overseas Admissions",
            "content": "Building AI tools for the education sector. Focus on automation and scale.",
        },
    )
    assert r.status_code == 201

    r = await client.get("/api/v1/data/branding/power")
    assert r.status_code == 200
    body = r.json()
    assert body["total_posts_30d"] >= 1
    assert "linkedin" in body["platforms_active"]


# ── Fraud Detection ────────────────────────────────────────────────────────────

async def test_fraud_detection_clean_org(client):
    r = await client.post("/api/v1/data/fraud/detect")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "full_scan"
    assert body["signals_found"] >= 0
    assert isinstance(body["signals"], list)
    assert isinstance(body["risk_breakdown"], dict)


async def test_fraud_detection_finds_anomaly(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "Found fake invoice from unknown vendor with inflated charges",
            "split_lines": False,
        },
    )
    assert r.status_code == 200

    r = await client.post("/api/v1/data/fraud/detect")
    assert r.status_code == 200
    body = r.json()
    assert body["signals_found"] >= 1
    categories = [s["category"] for s in body["signals"]]
    assert any(c in categories for c in ["invoice_fraud", "phantom_vendor"])


async def test_fraud_layer_report(client):
    r = await client.get("/api/v1/data/fraud/layer")
    assert r.status_code == 200
    body = r.json()
    assert "fraud_risk_score" in body
    assert 0 <= body["fraud_risk_score"] <= 100
    assert isinstance(body["recommendations"], list)


async def test_fraud_layer_via_layers(client):
    r = await client.get("/api/v1/layers/fraud-detection")
    assert r.status_code == 200
    body = r.json()
    assert "fraud_risk_score" in body


async def test_fraud_detection_requires_admin(client):
    from app.core.security import create_access_token
    staff_token = create_access_token(
        {"id": 4, "email": "staff@org1.com", "role": "STAFF", "org_id": 1, "token_version": 1}
    )
    r = await client.post(
        "/api/v1/data/fraud/detect",
        headers={"Authorization": f"Bearer {staff_token}"},
    )
    assert r.status_code == 403


async def test_fraud_scan_utility():
    from app.services.data_collection import _scan_for_fraud

    result = _scan_for_fraud("fake invoice from unknown vendor")
    assert len(result) >= 1
    categories = [r["category"] for r in result]
    assert "invoice_fraud" in categories or "phantom_vendor" in categories

    result2 = _scan_for_fraud("normal business meeting about strategy")
    assert len(result2) == 0


# ── AI News Digest ─────────────────────────────────────────────────────────────

async def test_news_digest_default_interests(client):
    r = await client.post("/api/v1/data/news/digest")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) > 0
    assert len(body["items"]) <= 10
    assert body["memory_keys"]
    assert body["interests_matched"]
    for item in body["items"]:
        assert "title" in item
        assert "summary" in item
        assert "relevance_tag" in item
        assert 0 <= item["relevance_score"] <= 100


async def test_news_digest_custom_interests(client):
    r = await client.post(
        "/api/v1/data/news/digest",
        json={
            "interests": ["education", "startup", "automation"],
            "max_items": 5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) <= 5
    assert body["memory_keys"]


async def test_news_digest_feeds_memory(client):
    r = await client.post("/api/v1/data/news/digest")
    assert r.status_code == 200
    body = r.json()
    assert len(body["memory_keys"]) >= 1
    # Verify memory was written
    mem_r = await client.get("/api/v1/memory/profile")
    assert mem_r.status_code == 200
    keys = [m["key"] for m in mem_r.json()]
    assert any(k.startswith("news.digest.") for k in keys)


async def test_news_digest_max_items_limit(client):
    r = await client.post(
        "/api/v1/data/news/digest",
        json={"interests": ["ai"], "max_items": 3},
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 3


# ── Ethical Boundary Layer ─────────────────────────────────────────────────────

async def test_ethical_boundary_clean_org(client):
    r = await client.get("/api/v1/data/ethics/boundary")
    assert r.status_code == 200
    body = r.json()
    assert "ethics_score" in body
    assert 0 <= body["ethics_score"] <= 100
    assert isinstance(body["violations"], list)
    assert isinstance(body["compliance_areas"], list)
    assert isinstance(body["recommendations"], list)
    assert len(body["compliance_areas"]) >= 3


async def test_ethical_boundary_detects_violation(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "Dark pattern detected in user flow that tries to manipulate and deceive users",
            "split_lines": False,
        },
    )
    assert r.status_code == 200

    r = await client.get("/api/v1/data/ethics/boundary")
    assert r.status_code == 200
    body = r.json()
    assert body["violations_found"] >= 1
    categories = [v["category"] for v in body["violations"]]
    assert "manipulation" in categories


async def test_ethical_boundary_via_layers(client):
    r = await client.get("/api/v1/layers/ethical-boundary")
    assert r.status_code == 200
    body = r.json()
    assert "ethics_score" in body
    assert "active_guardrails" in body


async def test_ethical_boundary_privacy_violation(client):
    r = await client.post(
        "/api/v1/data/collect",
        json={
            "source": "manual",
            "target": "notes",
            "content": "Tracking user personal data without consent and surveillance of activity",
            "split_lines": False,
        },
    )
    assert r.status_code == 200

    r = await client.get("/api/v1/data/ethics/boundary")
    assert r.status_code == 200
    body = r.json()
    categories = [v["category"] for v in body["violations"]]
    assert "privacy_violation" in categories
